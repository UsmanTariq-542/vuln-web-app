import sys
from pathlib import Path

# Make the 'app' package importable regardless of the launch directory
# (e.g. `uv run backend/app/main.py` from the project root, or
# `python app/main.py` from within backend/). Must run before any
# `from app...` import below.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import os
import secrets

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes.auth import router as auth_router
from app.db.session import init_db

PROJECT_ROOT = BACKEND_DIR.parent

app = FastAPI()

# VULN-4 remediated: secret key is sourced from the SECRET_KEY environment
# variable, with cookies scoped to https_only and a 30-minute max_age.
# See .claude/specs/session-hijacking-fix.md.
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    print(
        "WARNING: SECRET_KEY environment variable is not set. "
        "Using a randomly generated ephemeral key for this run only; "
        "all sessions will be invalidated on restart.",
        file=sys.stderr,
    )
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    https_only=True,
    max_age=1800,
)

# VULN-7: No Rate Limiting (intentional, by omission). No throttling
# middleware is registered anywhere in this file -- do not add one.

app.include_router(auth_router)

app.mount(
    "/static/css",
    StaticFiles(directory=str(PROJECT_ROOT / "frontend" / "static" / "css")),
    name="css",
)
app.mount(
    "/static/images",
    StaticFiles(directory=str(PROJECT_ROOT / "frontend" / "static" / "images")),
    name="images",
)

init_db()

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 3001))
    uvicorn.run(app, host="0.0.0.0", port=port)
