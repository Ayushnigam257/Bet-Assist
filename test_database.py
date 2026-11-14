import sqlite3
import tempfile
import unittest
from pathlib import Path

from database import Database


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "test.sqlite3")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_login_account_uses_hashed_password_and_authenticates(self) -> None:
        self.assertFalse(self.database.has_login_account())
        with self.assertRaises(ValueError):
            self.database.create_login_account("operator", "short")

        self.database.create_login_account("operator", "strong-pass-123")

        self.assertTrue(self.database.has_login_account())
        self.assertTrue(self.database.authenticate("OPERATOR", "strong-pass-123"))
        self.assertFalse(self.database.authenticate("operator", "wrong-pass"))
        self.assertFalse(self.database.authenticate("unknown", "strong-pass-123"))
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT password_salt, password_hash FROM login_account"
            ).fetchone()
        self.assertNotEqual(row["password_hash"], b"strong-pass-123")
        with self.assertRaises(ValueError):
            self.database.create_login_account("another", "strong-pass-123")

    def test_saves_and_lists_match_user_and_entry(self) -> None:
        self.database.save_match(None, 101, "2026-11-14", "Falcons vs Hawks", "Falcons, Hawks")
        match = self.database.list_matches()[0]
        self.database.save_user(
            None,
            {
                "name": "Example user",
                "state_ref": "North",
                "phone": "",
                "match_comm_1": "",
                "match_comm_2": "",
                "session_comm_1": "",
                "session_comm_2": "",
                "match_patti_1": "",
                "match_patti_2": "",
                "session_patti_1": "",
                "session_patti_2": "",
                "cutting_reference": "",
                "limit_mode": "",
                "limit_amount": 0,
                "patti_match": 0,
                "patti_session": 0,
                "patti_meter": 0,
                "session_commission": 0,
                "match_commission": 0,
                "match_commission_all": 0,
                "match_dibba": 0,
                "session_dibba": 0,
                "show_dibba_user": 0,
                "cutting_user": 0,
                "dibba_account": 0,
            },
        )
        user = self.database.list_users()[0]
        self.database.save_entry(
            None,
            {
                "match_id": match["id"],
                "user_id": user["id"],
                "entry_date": "2026-11-14",
                "entry_type": "Match",
                "patti_number": "",
                "rate": 2.5,
                "amount": 100,
                "mode": "A",
                "team": "Falcons",
                "session": "",
                "runs": "",
                "yes_no": "",
            },
        )

        entries = self.database.list_entries(match_id=match["id"])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["user_name"], "Example user")
        self.assertEqual(entries[0]["amount"], 100)

    def test_match_result_can_be_declared_and_undeclared(self) -> None:
        self.database.save_match(None, 101, "2026-11-14", "Falcons vs Hawks", "Falcons, Hawks")
        match = self.database.list_matches()[0]
        self.database.set_result(match["id"], "Declared", "Falcons")
        updated = self.database.list_matches()[0]
        self.assertEqual(updated["result"], "Declared")
        self.assertEqual(updated["winner"], "Falcons")
        self.database.set_result(match["id"], "Undeclared", "")
        self.assertEqual(self.database.list_matches()[0]["winner"], "")

    def test_match_with_entries_cannot_be_deleted(self) -> None:
        self.database.save_match(None, 101, "2026-11-14", "Falcons vs Hawks", "Falcons, Hawks")
        match = self.database.list_matches()[0]
        self.database.save_user(
            None,
            {
                "name": "Example user",
                "state_ref": "",
                "phone": "",
                "match_comm_1": "",
                "match_comm_2": "",
                "session_comm_1": "",
                "session_comm_2": "",
                "match_patti_1": "",
                "match_patti_2": "",
                "session_patti_1": "",
                "session_patti_2": "",
                "cutting_reference": "",
                "limit_mode": "",
                "limit_amount": 0,
                "patti_match": 0,
                "patti_session": 0,
                "patti_meter": 0,
                "session_commission": 0,
                "match_commission": 0,
                "match_commission_all": 0,
                "match_dibba": 0,
                "session_dibba": 0,
                "show_dibba_user": 0,
                "cutting_user": 0,
                "dibba_account": 0,
            },
        )
        user = self.database.list_users()[0]
        self.database.save_entry(
            None,
            {
                "match_id": match["id"],
                "user_id": user["id"],
                "entry_date": "2026-11-14",
                "entry_type": "Match",
                "patti_number": "",
                "rate": 2,
                "amount": 10,
                "mode": "A",
                "team": "Falcons",
                "session": "",
                "runs": "",
                "yes_no": "",
            },
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.delete_match(match["id"])


if __name__ == "__main__":
    unittest.main()
