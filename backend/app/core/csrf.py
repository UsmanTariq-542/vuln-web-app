import secrets


def generate_csrf_token() -> str:
    return secrets.token_hex(32)


def verify_csrf_token(session_token: str | None, submitted_token: str | None) -> bool:
    if not session_token or not submitted_token:
        return False
    return secrets.compare_digest(session_token, submitted_token)
