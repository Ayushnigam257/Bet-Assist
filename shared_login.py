import hashlib
import hmac

from shared_login_credentials import (
    PASSWORD_HASH_HEX,
    PASSWORD_HASH_ITERATIONS,
    PASSWORD_SALT_HEX,
    USERNAME,
)


def verify_password(password: str, salt_hex: str, expected_hash_hex: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(expected_hash_hex)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS
    )
    return hmac.compare_digest(candidate, expected_hash)


def authenticate(username: str, password: str) -> bool:
    username_matches = hmac.compare_digest(
        username.strip().casefold().encode("utf-8"),
        USERNAME.casefold().encode("utf-8"),
    )
    password_matches = verify_password(
        password, PASSWORD_SALT_HEX, PASSWORD_HASH_HEX
    )
    return username_matches and password_matches
