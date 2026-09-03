"""auth/：平台身份（JWT）与供应商凭证加密库（后端设计 §7.2，P3）。

JWT 为零依赖 HS256 实现；凭证用 AES-GCM（主密钥来自 CREDENTIAL_MASTER_KEY）。
鉴权开关：AUTH_ENABLED=1 时 REST 强制 Bearer；默认 off（演示链路兼容）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass

from tools.base import ToolCall, ToolResult
from tools.base import ExecCtx
from engine.types import RunOutcome

AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "0") == "1"
JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_TTL_SECONDS = int(os.environ.get("JWT_TTL_SECONDS", "3600"))

_MASTER_KEY = os.environ.get("CREDENTIAL_MASTER_KEY", "")


# ---------------------------------------------------------------------------
# JWT（HS256，零依赖实现）
# ---------------------------------------------------------------------------


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(payload: dict, secret: str | None = None, ttl: int | None = None) -> str:
    secret = secret or JWT_SECRET
    ttl = JWT_TTL_SECONDS if ttl is None else ttl
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    body = {**payload, "iat": now, "exp": now + ttl}
    signing = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(body).encode())}"
    sig = hmac.new(secret.encode(), signing.encode(), hashlib.sha256).digest()
    return f"{signing}.{_b64url(sig)}"


def verify_token(token: str, secret: str | None = None) -> dict | None:
    """校验签名与有效期；失败返回 None（不抛）。"""
    secret = secret or JWT_SECRET
    try:
        head, body, sig = token.split(".")
        expected = hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(sig, _b64url(expected)):
            return None
        payload = json.loads(_b64url_decode(body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:  # noqa: BLE001 — 任何畸形 token 一律拒绝
        return None


# ---------------------------------------------------------------------------
# 凭证加密（AES-GCM 经 hashlib? —— 标准库无 AES；改用 Fernet 兼容实现：
# 这里采用 XChaCha? 标准库同样没有。方案：cryptography 包（pip 依赖，常见且纯轮）。
# 为零新增依赖，用 AES-256-GCM 的替代：HMAC-SHA256 流加密不安全，故直接依赖
# cryptography（ requirements 明确列入）。
# ---------------------------------------------------------------------------


class CredentialVault:
    """租户凭证库：写即加密、读即解密；进程内 + Postgres 持久化由装配层组合。"""

    def __init__(self, master_key: str) -> None:
        if not master_key:
            raise ValueError("CREDENTIAL_MASTER_KEY is required for CredentialVault")
        self._key = base64.urlsafe_b64decode(master_key + "=" * (-len(master_key) % 4))[:32]

    def encrypt(self, plaintext: str) -> bytes:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = secrets.token_bytes(12)
        return nonce + AESGCM(self._key).encrypt(nonce, plaintext.encode(), None)

    def decrypt(self, blob: bytes) -> str:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        return AESGCM(self._key).decrypt(blob[:12], blob[12:], None).decode()


# ---------------------------------------------------------------------------
# 策略引擎占位（保留 import 面稳定性；供 hooks 策略替换）
# ---------------------------------------------------------------------------


class NoopPolicyEngine:
    async def pre_tool_use(self, call: ToolCall, ctx: ExecCtx) -> object | None:
        return None

    async def post_tool_use(self, call: ToolCall, result: ToolResult, ctx: ExecCtx) -> None:
        return None

    async def post_run(self, outcome: RunOutcome) -> None:
        return None
