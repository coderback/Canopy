"""`python -m canopy api` or `python -m canopy worker`.

Both set the selector event loop first (needed for psycopg async on Windows).
"""

import asyncio
import sys

from .core.loop import configure_event_loop


def main() -> None:
    configure_event_loop()
    command = sys.argv[1] if len(sys.argv) > 1 else "api"
    if command == "api":
        import uvicorn

        from .app import create_app

        # loop="none": keep the policy set above instead of uvicorn choosing one.
        uvicorn.run(create_app(), host="0.0.0.0", port=8000, loop="none")
    elif command == "worker":
        from .core.logging import configure_logging
        from .jobs.app import app as jobs

        configure_logging()

        async def run() -> None:
            async with jobs.open_async():
                await jobs.run_worker_async(queues=["xero", "mapping"])

        asyncio.run(run())
    elif command == "openapi":
        # The contract the web app's TypeScript types are generated from.
        import json

        from .app import create_app

        print(json.dumps(create_app(with_jobs=False).openapi(), indent=2, sort_keys=True))
    else:
        sys.exit(f"unknown command {command!r}: use 'api', 'worker' or 'openapi'")


if __name__ == "__main__":
    main()
