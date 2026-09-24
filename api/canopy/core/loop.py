"""psycopg's async mode can't run on Windows' default ProactorEventLoop.

Production runs in Linux containers, so this only matters for local development
and tests on Windows. Call `configure_event_loop()` before any loop is created.
"""

import asyncio
import sys


def configure_event_loop() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
