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
def download_db():
    # VULN-6: Exposed Database (intentional). No auth check whatsoever --
    # anyone who knows this URL can download the entire SQLite file.
    return FileResponse(DB_PATH, filename="vulnerable_app.db")


@router.get("/search")
def search_user(q: str = ""):
    # VULN-3: Reflected XSS (intentional), plus SQL Injection via string
    # concatenation, plus raw exception-message leakage. None of the three
    # are accidental -- do not parameterize the query or escape the output.
    try:
        conn = get_db()
        query = (
            "SELECT username, email FROM users WHERE username LIKE '%" + q
            + "%' OR email LIKE '%" + q + "%'"
        )
        rows = conn.execute(query).fetchall()
        conn.close()

        results_html = "".join(
            f"<li>{row['username']} ({row['email']})</li>" for row in rows
        )
        body = f"<h2>Search results for: {q}</h2><ul>{results_html}</ul>"
        return HTMLResponse(body)
    except Exception as e:
        return HTMLResponse(f"<p>Search error: {e}</p>", status_code=500)


@router.get("/welcome")
def welcome_page(request: Request):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=302)

    # VULN-2: Stored XSS (intentional). The username is substituted into the
    # template with no escaping -- a username stored with a <script>/<img
    # onerror> payload executes here on every load.
    html = _read_template("dashboard.html")
    html = html.replace("{{username}}", request.session["username"])
    return HTMLResponse(html)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
