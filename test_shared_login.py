import hashlib
import unittest

from shared_login import authenticate, verify_password
from shared_login_credentials import (
    PASSWORD_HASH_HEX,
    PASSWORD_SALT_HEX,
    USERNAME,
)


class SharedLoginTests(unittest.TestCase):
    def test_password_hash_verification(self) -> None:
        password = "test-password-123"
        salt = b"0123456789abcdef"
        expected = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, 600_000
        ).hex()

        self.assertTrue(verify_password(password, salt.hex(), expected))
        self.assertFalse(verify_password("incorrect", salt.hex(), expected))
        self.assertFalse(verify_password(password, "invalid", expected))

    def test_shared_login_configuration_is_present(self) -> None:
        self.assertEqual(USERNAME, "main")
        self.assertEqual(len(bytes.fromhex(PASSWORD_SALT_HEX)), 16)
        self.assertEqual(len(bytes.fromhex(PASSWORD_HASH_HEX)), 32)
        self.assertFalse(authenticate("not-main", "irrelevant"))


if __name__ == "__main__":
    unittest.main()
