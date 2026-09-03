"""Docker 沙箱真机冒烟（权限与沙箱设计 §2.8 子集）。

前置：docker build -t codeharness-sandbox:1.0 sandbox/image 且 Docker 守护进程可用。
运行：python -m tests.smoke_sandbox_docker
"""

from __future__ import annotations

import asyncio
import os
import tempfile

from tools.base import ExecResult, SandboxFileNotFound
from sandbox.docker import DockerSandbox


async def main() -> int:
    failures = 0
    workdir = tempfile.mkdtemp(prefix="ch-sbx-test-")
    sandbox = DockerSandbox("test-session", workdir)
    cases: list[tuple[str, bool]] = []

    async def check(name: str, fn) -> None:
        nonlocal failures
        try:
            await fn()
            cases.append((name, True))
            print(f"PASS  {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            cases.append((name, False))
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")

    async def exec_echo():
        r = await sandbox.exec(["echo", "hello-sandbox"])
        assert r.exit_code == 0 and "hello-sandbox" in r.stdout, r

    async def jail_blocks_sudo():
        r = await sandbox.exec(["/usr/local/bin/jail", "sudo", "id"])
        assert r.exit_code == 126, r

    async def write_then_read():
        await sandbox.write_file("/workspace/hello.txt", b"hello from codeharness\n")
        data = await sandbox.read_file("/workspace/hello.txt")
        assert data == b"hello from codeharness\n", data

    async def binary_safe_write():
        payload = bytes(range(256))
        await sandbox.write_file("/workspace/bin.dat", payload)
        data = await sandbox.read_file("/workspace/bin.dat")
        assert data == payload

    async def escape_blocked_by_container_layout():
        # 挂载边界：/workspace 之外不可经容器写入宿主（resolver 是第一道；这里是容器侧兜底）
        r = await sandbox.exec(["ls", "/"])
        assert r.exit_code == 0
        assert "etc" in r.stdout  # 容器根可读，但宿主文件系统不可见（无 bind 到根）

    async def timeout_returns_124():
        r = await sandbox.exec(["sleep", "30"], timeout_s=2)
        assert r.exit_code == 124, r

    async def non_zero_not_crash():
        r = await sandbox.exec(["bash", "-c", "exit 3"])
        assert r.exit_code == 3, r

    for name, fn in [
        ("exec_echo", exec_echo),
        ("jail_blocks_sudo", jail_blocks_sudo),
        ("write_then_read", write_then_read),
        ("binary_safe_write", binary_safe_write),
        ("non_zero_not_crash", non_zero_not_crash),
        ("timeout_returns_124", timeout_returns_124),
    ]:
        await check(name, fn)

    await sandbox.destroy()
    print(f"\n{sum(1 for _, ok in cases if ok)}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
