import hashlib

# VULN-5: Weak Password Storage (intentional).
# MD5 with no salt, no pepper, no key-derivation function. Do not "fix" this here --
# bcrypt/argon2 migration is a later, separate exercise.


def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    return hash_password(plain) == hashed
