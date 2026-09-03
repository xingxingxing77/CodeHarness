#!/usr/bin/env python3
"""jail 包装器：工具命令进入真实二进制前的最后一道闸（权限与沙箱设计 §2.7）。

- 拒绝提权/逃逸类二进制（sudo/su/mount/nsenter/unshare/setpriv/chmod/chown）
- 以最小环境执行（调用方已传 env 白名单）
- 本进程自身以非 root 运行（镜像 USER 1000）
"""

from __future__ import annotations

import os
import shutil
import sys

BLOCKED_BINARIES = {
    "sudo", "su", "doas", "mount", "umount", "nsenter", "unshare",
    "setpriv", "capsh", "chroot", "pivot_root", "modprobe", "insmod",
    "useradd", "usermod", "userdel", "groupadd", "passwd", "chsh",
    "chmod", "chown", "setcap", "getcap", "iptables", "ip",
}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("jail: no command given", file=sys.stderr)
        return 126

    target = argv[1]
    binary = os.path.basename(target)

    if binary in BLOCKED_BINARIES:
        print(f"jail: blocked binary: {binary}", file=sys.stderr)
        return 126

    path = shutil.which(target)
    if path is None:
        print(f"jail: command not found: {target}", file=sys.stderr)
        return 127

    try:
        os.execvp(path, argv[1:])
    except OSError as exc:
        print(f"jail: exec failed: {exc}", file=sys.stderr)
        return 126
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
