"""GitHub Copilot OAuth device-flow authentication.

Flow:
1. Device code request  → user visits URL and enters code
2. Poll for OAuth token → get GitHub access token
3. Use token directly   → ``Authorization: Bearer <token>`` to Copilot API

解耦改造（api内核搬迁细则 D2）：令牌持久化经 TokenStore 注入，不再直连
~/.openharness 目录。提供进程内与文件两个实现；平台形态由凭证库实现该协议。

Supports two deployment types:
- **github.com** — public GitHub, API at ``https://api.githubcopilot.com``
- **enterprise**  — GitHub Enterprise (data-residency / self-hosted),
  API at ``https://copilot-api.<domain>``
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# OAuth client ID registered by OpenCode for Copilot integrations.
# 运营项：商用平台应注册自己的 GitHub App 并替换此 client_id。
COPILOT_CLIENT_ID = "Ov23li8tweQw6odWQebz"

COPILOT_DEFAULT_API_BASE = "https://api.githubcopilot.com"

# Safety margin added to each poll interval to avoid server-side rate limits.
_POLL_SAFETY_MARGIN = 3.0  # seconds


def copilot_api_base(enterprise_url: str | None = None) -> str:
    """Return the Copilot API base URL."""
    if enterprise_url:
        domain = enterprise_url.replace("https://", "").replace("http://", "").rstrip("/")
        return f"https://copilot-api.{domain}"
    return COPILOT_DEFAULT_API_BASE


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeviceCodeResponse:
    """Parsed response from the GitHub device-code endpoint."""

    device_code: str
    user_code: str
    verification_uri: str
    interval: int
    expires_in: int


@dataclass
class CopilotAuthInfo:
    """Persisted + runtime auth state for Copilot."""

    github_token: str
    enterprise_url: str | None = None

    @property
    def api_base(self) -> str:
        return copilot_api_base(self.enterprise_url)


class TokenStore(Protocol):
    """Copilot 令牌持久化协议（平台侧由凭证库实现）。"""

    def load(self) -> CopilotAuthInfo | None: ...

    def save(self, info: CopilotAuthInfo) -> None: ...

    def clear(self) -> None: ...


class MemoryTokenStore:
    """进程内实现（测试 / 无持久化部署）。"""

    def __init__(self) -> None:
        self._info: CopilotAuthInfo | None = None

    def load(self) -> CopilotAuthInfo | None:
        return self._info

    def save(self, info: CopilotAuthInfo) -> None:
        self._info = info

    def clear(self) -> None:
        self._info = None


class FileTokenStore:
    """单机文件实现（atomic write，0600），替代供体的直连 ~/.openharness 落盘。"""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> CopilotAuthInfo | None:
        if not self._path.exists():
            return None
        try:
            data: dict[str, Any] = json.loads(self._path.read_text(encoding="utf-8"))
            token = data.get("github_token")
            if not token:
                return None
            return CopilotAuthInfo(github_token=token, enterprise_url=data.get("enterprise_url"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to read Copilot auth file: %s", exc)
            return None

    def save(self, info: CopilotAuthInfo) -> None:
        import json as _json
        import os

        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {"github_token": info.github_token}
        if info.enterprise_url:
            payload["enterprise_url"] = info.enterprise_url
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(_json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self._path)
        try:
            os.chmod(self._path, 0o600)
        except OSError:  # noqa: BLE001 — Windows 上 0600 语义受限
            pass
        log.info("Copilot auth saved to %s", self._path)

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()
            log.info("Copilot auth cleared.")


# ---------------------------------------------------------------------------
# OAuth device flow (synchronous – called from CLI/admin flows)
# ---------------------------------------------------------------------------


def request_device_code(
    *,
    client_id: str = COPILOT_CLIENT_ID,
    github_domain: str = "github.com",
) -> DeviceCodeResponse:
    """Start the OAuth device flow and return the device/user codes."""
    url = f"https://{github_domain}/login/device/code"
    resp = httpx.post(
        url,
        json={"client_id": client_id, "scope": "read:user"},
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return DeviceCodeResponse(
        device_code=data["device_code"],
        user_code=data["user_code"],
        verification_uri=data["verification_uri"],
        interval=data.get("interval", 5),
        expires_in=data.get("expires_in", 900),
    )


def poll_for_access_token(
    device_code: str,
    interval: int,
    *,
    client_id: str = COPILOT_CLIENT_ID,
    github_domain: str = "github.com",
    timeout: float = 900,
    progress_callback: Any | None = None,
) -> str:
    """Poll GitHub until the user authorises, returning the OAuth access token."""
    url = f"https://{github_domain}/login/oauth/access_token"
    poll_interval = float(interval)
    deadline = time.monotonic() + timeout
    start = time.monotonic()
    poll_count = 0

    while time.monotonic() < deadline:
        time.sleep(poll_interval + _POLL_SAFETY_MARGIN)
        poll_count += 1
        if progress_callback is not None:
            progress_callback(poll_count, time.monotonic() - start)
        resp = httpx.post(
            url,
            json={
                "client_id": client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        if "access_token" in data:
            return data["access_token"]

        error = data.get("error", "")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            server_interval = data.get("interval")
            if isinstance(server_interval, (int, float)) and server_interval > 0:
                poll_interval = float(server_interval)
            else:
                poll_interval += 5.0
            continue
        # Any other error is terminal.
        desc = data.get("error_description", error)
        raise RuntimeError(f"OAuth device flow failed: {desc}")

    raise RuntimeError("OAuth device flow timed out waiting for user authorisation.")
