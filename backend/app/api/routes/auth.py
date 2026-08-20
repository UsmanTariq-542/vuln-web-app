import html
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.db.session import DB_PATH, get_db
from app.services import auth_service

router = APIRouter()

# backend/app/api/routes/auth.py -> routes -> api -> app -> backend -> <project root>
TEMPLATES_DIR = Path(__file__).resolve().parents[4] / "frontend" / "templates"


def _read_template(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


@router.get("/")
def index():
    return RedirectResponse(url="/signup", status_code=302)


@router.get("/signup")
def signup_page():
    return HTMLResponse(_read_template("signup.html"))


@router.post("/signup")
def signup_post(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    return auth_service.signup(username, email, password)


@router.get("/login")
def login_page():
    return HTMLResponse(_read_template("login.html"))


@router.post("/login")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    return auth_service.login(request, username, password)


@router.get("/download/db")
def download_db(request: Request):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=302)

    # VULN-6 remediated: session-presence check gates access. Any
    # authenticated user may still download the file -- this app has no
    # role/admin system, so this is "authenticated only," not "admin only".
    # See .claude/specs/exposed-database-fix.md.
    return FileResponse(DB_PATH, filename="vulnerable_app.db")


@router.get("/search")
def search_user(q: str = ""):
    # VULN-3 remediated: query is parameterized (?-placeholder binding, same
    # pattern as auth_service.py's VULN-1 fix), q and result-row fields are
    # HTML-escaped before embedding, and the exception handler no longer
    # leaks exception detail. See .claude/specs/reflected-xss-fix.md.
    try:
        conn = get_db()
        like_pattern = f"%{q}%"
        rows = conn.execute(
            "SELECT username, email FROM users WHERE username LIKE ? OR email LIKE ?",
            (like_pattern, like_pattern),
        ).fetchall()
        conn.close()

        results_html = "".join(
            f"<li>{html.escape(row['username'])} ({html.escape(row['email'])})</li>"
            for row in rows
        )
        body = f"<h2>Search results for: {html.escape(q)}</h2><ul>{results_html}</ul>"
        return HTMLResponse(body)
    except Exception:
        return HTMLResponse("<p>Search error. Please try again.</p>", status_code=500)


@router.get("/welcome")
def welcome_page(request: Request):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=302)

    # VULN-2 remediated: the username is HTML-escaped before substitution so
    # a stored <script>/<img onerror> payload renders as inert literal text
    # instead of executing. See .claude/specs/stored-xss-fix.md.
    page_html = _read_template("dashboard.html")
    safe_username = html.escape(request.session["username"])
    page_html = page_html.replace("{{username}}", safe_username)
    return HTMLResponse(page_html)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
