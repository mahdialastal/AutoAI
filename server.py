"""Entry point: `python server.py` — starts FastAPI on localhost:8000."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure src/ is on the path when running from the project root.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    import uvicorn
    host = os.environ.get("AUTOSHORTS_HOST", "127.0.0.1")
    port = int(os.environ.get("AUTOSHORTS_PORT", "8000"))
    reload = os.environ.get("AUTOSHORTS_RELOAD", "").lower() in ("1", "true", "yes")
    uvicorn.run(
        "src.autoshorts.server.app:app",
        host=host, port=port, reload=reload,
    )


if __name__ == "__main__":
    main()
