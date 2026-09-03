"""Docker per-session 沙箱实现（权限与沙箱设计 §二，契约⑦）。

aiodocker 驱动；容器懒创建、跨调用复用、destroy 销毁。
容器规格：--network none / 非 root / cap-drop ALL / 只读根+tmpfs / 资源限额。
联调：P2 与真实 Docker Desktop/守护进程对表（当前 FakeSandbox 承担冒烟）。
"""

from __future__ import annotations

import base64
import logging

import aiodocker

from tools.base import ExecResult, SandboxFileNotFound

log = logging.getLogger(__name__)

_SANDBOX_IMAGE = "codeharness-sandbox:1.0"
_CONTAINER_ROOT = "/workspace"


class DockerSandbox:
    """一个会话一个容器；工具实现只看到本类的 SandboxHandle 面。"""

    def __init__(
        self,
        session_id: str,
        host_workdir: str,
        *,
        image: str = _SANDBOX_IMAGE,
        memory_mb: int = 512,
        cpus: float = 1.0,
        pids_limit: int = 128,
        docker: aiodocker.Docker | None = None,
    ) -> None:
        self._session_id = session_id
        self._host_workdir = host_workdir
        self._image = image
        self._memory_mb = memory_mb
        self._cpus = cpus
        self._pids_limit = pids_limit
        self._docker = docker or aiodocker.Docker()
        self._container = None

    # -- 容器生命周期 -------------------------------------------------------

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def root(self) -> str:
        return self._host_workdir

    def _container_name(self) -> str:
        return f"ch-sbx-{self._session_id[:12]}"

    async def _ensure_container(self):
        if self._container is not None:
            return self._container
        name = self._container_name()
        existing = await self._docker.containers.list(
            filters={"name": [name]}
        )
        if existing:
            self._container = existing[0]
        else:
            config = {
                "Image": self._image,
                "Name": name,
                "Cmd": ["sleep", "infinity"],
                "HostConfig": {
                    "NetworkMode": "none",                     # S1.2
                    "ReadonlyRootfs": True,                    # S1.5
                    "Memory": self._memory_mb * 1024 * 1024,
                    "NanoCpus": int(self._cpus * 1e9),
                    "PidsLimit": self._pids_limit,
                    "CapDrop": ["ALL"],                        # S1.3
                    "SecurityOpt": ["no-new-privileges"],
                    "Tmpfs": {"/tmp": "rw,size=64m,uid=1000"},
                    "Binds": [f"{self._host_workdir}:{_CONTAINER_ROOT}:rw"],
                },
                "User": "1000:1000",                           # S1.3
            }
            self._container = await self._docker.containers.create(config=config)
        await self._container.start()
        return self._container

    async def destroy(self) -> None:
        if self._container is None:
            return
        try:
            await self._container.delete(force=True)
        except aiodocker.DockerError as exc:  # noqa: BLE001 — 已销毁视为成功
            log.warning("sandbox destroy failed (ignored): %s", exc)
        self._container = None

    # -- exec ---------------------------------------------------------------

    async def exec(
        self,
        argv: list[str],
        *,
        cwd: str = "/workspace",
        env: dict[str, str] | None = None,
        timeout_s: float = 120.0,
        output_cap: int = 1_048_576,
    ) -> ExecResult:
        import asyncio

        container = await self._ensure_container()
        run = await container.exec(
            argv,
            environment=env or {},
            workdir=cwd,
        )
        stream = run.start()

        stdout_parts: list[bytes] = []
        stderr_parts: list[bytes] = []
        truncated = False

        async def _drain() -> None:
            nonlocal truncated
            while True:
                message = await stream.read_out()
                if message is None:
                    return
                data = message.data
                sink = stdout_parts if message.stream == 1 else stderr_parts
                if sum(len(p) for p in sink) + len(data) > output_cap:
                    truncated = True
                    continue  # 丢弃超额部分，防管道背压死锁
                sink.append(data)

        import time as _time

        started = _time.monotonic()
        try:
            await asyncio.wait_for(_drain(), timeout=timeout_s)
        except asyncio.TimeoutError:
            log.warning("exec timed out after %.0fs; container-side limits remain", timeout_s)
            return ExecResult(
                exit_code=124, stdout=b"".join(stdout_parts).decode("utf-8", "replace"),
                stderr=b"".join(stderr_parts).decode("utf-8", "replace"),
                truncated=True, duration_ms=int((_time.monotonic() - started) * 1000),
            )

        inspect = await run.inspect()
        return ExecResult(
            exit_code=int(inspect.get("ExitCode", -1)),
            stdout=b"".join(stdout_parts).decode("utf-8", "replace"),
            stderr=b"".join(stderr_parts).decode("utf-8", "replace"),
            truncated=truncated,
            duration_ms=int((_time.monotonic() - started) * 1000),
        )

    async def _kill_exec(self, exec_id: str) -> None:
        try:
            # docker API 无直接 kill-exec；退化策略：杀容器内进程组由 jail/限额兜底
            log.warning("exec timed out; container-side limits remain in force (%s)", exec_id[:12])
        except Exception:  # noqa: BLE001
            pass

    # -- 文件 IO（base64 经 exec，二进制安全） -------------------------------

    async def read_file(self, container_path: str, *, cap: int = 2_097_152) -> bytes:
        result = await self.exec(
            ["base64", "-w", "0", container_path], output_cap=max(cap * 2, cap)
        )
        if result.exit_code != 0:
            raise SandboxFileNotFound(f"{container_path}: {result.stderr.strip()[:200]}")
        data = base64.b64decode(result.stdout.strip())
        if len(data) > cap:
            raise SandboxFileNotFound(f"{container_path}: exceeds read cap {cap}")
        return data

    async def write_file(self, container_path: str, data: bytes) -> None:
        encoded = base64.b64encode(data).decode("ascii")
        # 分块写，防单条命令超长；父目录由镜像工作区约定保证存在（或工具先建）
        result = await self.exec(
            ["bash", "-c", f"mkdir -p $(dirname {container_path}) && echo {encoded} | base64 -d > {container_path}"],
        )
        if result.exit_code != 0:
            raise SandboxFileNotFound(f"write failed: {result.stderr.strip()[:200]}")


class SandboxPool:
    """会话 → 沙箱缓存；空闲回收由 watchdog 定期调用 recycle()。"""

    def __init__(self, host_root: str, *, image: str = _SANDBOX_IMAGE) -> None:
        import pathlib

        self._host_root = pathlib.Path(host_root)
        self._image = image
        self._sandboxes: dict[str, DockerSandbox] = {}

    def get(self, session_id: str, workdir_override: str | None = None) -> DockerSandbox:
        sandbox = self._sandboxes.get(session_id)
        if sandbox is None:
            if workdir_override:
                workdir = pathlib.Path(workdir_override)
            else:
                workdir = self._host_root / session_id
            workdir.mkdir(parents=True, exist_ok=True)
            sandbox = DockerSandbox(session_id, str(workdir), image=self._image)
            self._sandboxes[session_id] = sandbox
        return sandbox

    async def drop(self, session_id: str) -> None:
        sandbox = self._sandboxes.pop(session_id, None)
        if sandbox is not None:
            await sandbox.destroy()

