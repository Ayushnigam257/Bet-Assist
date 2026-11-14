import getpass
import hashlib
import secrets
from pathlib import Path


OUTPUT = Path(__file__).with_name("shared_login_credentials.py")
ITERATIONS = 600_000


def main() -> None:
    username = input("Shared login username: ").strip()
    if not username:
        raise SystemExit("Username cannot be empty.")

    password = getpass.getpass("New shared password (at least 8 characters): ")
    if len(password) < 8:
        raise SystemExit("Password must contain at least 8 characters.")
    confirmation = getpass.getpass("Confirm new shared password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")

    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, ITERATIONS
    )
    OUTPUT.write_text(
        "\n".join(
            (
                f"USERNAME = {username!r}",
                f"PASSWORD_SALT_HEX = {salt.hex()!r}",
                f"PASSWORD_HASH_HEX = {password_hash.hex()!r}",
                f"PASSWORD_HASH_ITERATIONS = {ITERATIONS}",
                "",
            )
        ),
        encoding="utf-8",
    )
    print(f"Shared login credentials updated in {OUTPUT.name}.")
    print("Commit and distribute this file for the new login to apply to clones.")


if __name__ == "__main__":
    main()
