import sqlite3

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.core.security import hash_password, verify_password
from app.db.session import get_db

# VULN-1: SQL Injection (intentional).
# Every query below is built with plain string concatenation of user-controlled
# input -- no "?" placeholders, no parameter tuples, no ORM. Do not parameterize
# these; that is a later remediation exercise, not part of this baseline.


def signup(username: str, email: str, password: str):
    if not username or not email or not password:
        return HTMLResponse("Username, email, and password are all required.", status_code=400)

    hashed = hash_password(password)

    conn = get_db()
    try:
        query = (
            "INSERT INTO users (username, email, password) VALUES ('"
            + username + "', '" + email + "', '" + hashed + "')"
        )
        conn.execute(query)
        conn.commit()
    except sqlite3.IntegrityError:
        return HTMLResponse("Username already exists", status_code=400)
    finally:
        conn.close()

    return RedirectResponse(url="/login", status_code=302)


def login(request: Request, username: str, password: str):
    if not username or not password:
        return JSONResponse({"success": False, "error": "Username and password are required."}, status_code=401)

    conn = get_db()
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    row = conn.execute(query).fetchone()
    conn.close()

    if row is None or not verify_password(password, row["password"]):
        return JSONResponse({"success": False, "error": "Invalid username or password."}, status_code=401)

    request.session["user_id"] = row["id"]
    request.session["username"] = row["username"]
    request.session["email"] = row["email"]

    return JSONResponse({"success": True, "redirect": "/welcome"})
