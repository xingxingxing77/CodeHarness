"""开发服务器启动脚本：Windows 上以 Selector 事件循环运行 uvicorn（psycopg 异步要求）。

用法：python scripts/run_server.py   # 127.0.0.1:8000
"""

import asyncio
import selectors
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402


def _loop_factory() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.new_event_loop()


def main() -> None:
    config = uvicorn.Config("server.main:app", host="127.0.0.1", port=8000, loop="none")
    server = uvicorn.Server(config)
    asyncio.run(server.serve(), loop_factory=_loop_factory)


if __name__ == "__main__":
    main()
