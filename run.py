#!/usr/bin/env python3
"""Start the built React dashboard and FastAPI backend on localhost:8000."""
from __future__ import annotations

import os
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent


def main() -> None:
    os.chdir(BASE_DIR)
    sys.path.insert(0, str(BASE_DIR))

    dist_index = BASE_DIR / "frontend" / "dist" / "index.html"
    if not dist_index.is_file():
        raise SystemExit(
            "Built React assets are missing. In the project directory run: "
            "npm ci && npm run build"
        )

    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "FastAPI server dependencies are missing. Run: "
            "python -m pip install -r requirements.txt"
        ) from exc

    host = os.environ.get("CASCADE_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("PORT", "8000"))
    except ValueError as exc:
        raise SystemExit("PORT must be an integer between 1 and 65535") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("PORT must be an integer between 1 and 65535")

    print(f"CASCADE SENTINEL · React + FastAPI · http://{host}:{port}", flush=True)
    print("Local-only by default. Stop with Ctrl+C.", flush=True)
    loop = "web_app:windows_selector_loop_factory" if sys.platform == "win32" else "auto"
    uvicorn.run("web_app:app", host=host, port=port, log_level="info", proxy_headers=False, loop=loop)


if __name__ == "__main__":
    main()
