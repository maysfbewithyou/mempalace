"""Allow running as: python -m mempalace [<subcommand>]

version: 0.2 (Phase 2a — added serve-http intercept)

The `serve-http` subcommand is intercepted here BEFORE delegating to cli.main()
so that we don't have to modify the upstream `cli.py` (keeps monthly D8 upstream
sync conflict-free — cli.py never deviates from upstream).

All other subcommands (init, mine, search, …) fall through to cli.main()
exactly as before.
"""

import sys


def _maybe_serve_http() -> bool:
    """If argv[1] == 'serve-http', start the HTTP wrapper and return True.

    Returns False otherwise so the caller falls through to cli.main().
    """
    if len(sys.argv) > 1 and sys.argv[1] == "serve-http":
        import argparse

        parser = argparse.ArgumentParser(
            prog="mempalace serve-http",
            description="Run the MemPalace HTTP/MCP wrapper (Phase 2a).",
        )
        parser.add_argument(
            "--host",
            default="0.0.0.0",
            help="Bind address (default: 0.0.0.0)",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=8000,
            help="Listen port (default: 8000)",
        )
        parser.add_argument(
            "--log-level",
            default="info",
            choices=["critical", "error", "warning", "info", "debug", "trace"],
            help="uvicorn log level (default: info)",
        )
        args = parser.parse_args(sys.argv[2:])

        from .http_server import run

        run(host=args.host, port=args.port, log_level=args.log_level)
        return True
    return False


if not _maybe_serve_http():
    from .cli import main

    main()
