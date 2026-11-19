import sqlite3
import tempfile
import unittest
from pathlib import Path

from database import Database, USER_FIELDS


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "test.sqlite3")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_user(self, name: str, state_ref: str = "") -> int:
        numeric_fields = {
            "limit_amount",
            "patti_match",
            "patti_session",
            "patti_meter",
            "session_commission",
            "match_commission",
            "match_commission_all",
            "match_dibba",
            "session_dibba",
            "show_dibba_user",
            "cutting_user",
            "dibba_account",
        }
        values = {field: 0 if field in numeric_fields else "" for field in USER_FIELDS}
        values.update(name=name, state_ref=state_ref)
        self.database.save_user(None, values)
        return int(self.database.list_users()[-1]["id"])

    def test_state_refs_are_reusable_and_separate_from_user_values(self) -> None:
        self.create_user("North user", "North")
        self.create_user("Another North user", "north")
        self.create_user("South user", "South")

        state_refs = self.database.list_state_refs()
        self.assertEqual([row["name"] for row in state_refs], ["North", "South"])
        north_id = int(state_refs[0]["id"])

        self.database.delete_state_refs([north_id])
        self.assertEqual(
            [row["name"] for row in self.database.list_state_refs()], ["South"]
        )
        self.assertEqual(
            {row["state_ref"] for row in self.database.list_users()},
            {"North", "north", "South"},
        )

        self.database = Database(self.database.path)
        self.assertEqual(
            [row["name"] for row in self.database.list_state_refs()], ["South"]
        )

    def test_state_ref_migration_backfills_existing_user_values(self) -> None:
        self.create_user("Existing user", "Central")
        with self.database.connect() as connection:
            connection.execute("DROP TABLE state_refs")

        self.database = Database(self.database.path)

        self.assertEqual(
            [row["name"] for row in self.database.list_state_refs()], ["Central"]
        )

    def test_books_audit_log_and_multi_match_entry_filters(self) -> None:
        self.database.save_match(None, 101, "2026-11-14", "Match one", "Falcons, Hawks")
        self.database.save_match(None, 102, "2026-11-15", "Match two", "Falcons, Hawks")
        matches = {row["code"]: row for row in self.database.list_matches()}
        user_id = self.create_user("Example user", "North")

        self.database.save_entry(
            None,
            {
                "match_id": matches[101]["id"],
                "user_id": user_id,
                "entry_date": "2026-11-14",
                "entry_type": "Match",
                "patti_number": "123",
                "rate": 2.5,
                "amount": 100,
                "mode": "A",
                "team": "Falcons",
                "session": "",
                "runs": "",
                "yes_no": "",
                "support": "manual",
                "charge": 2,
            },
        )
        self.database.save_entry(
            None,
            {
                "match_id": matches[102]["id"],
                "book_no": 2,
                "user_id": user_id,
                "entry_date": "2026-11-15",
                "entry_type": "Session",
                "patti_number": "",
                "rate": 3,
                "amount": 50,
                "mode": "K",
                "team": "",
                "session": "Morning",
                "runs": "7",
                "yes_no": "Yes",
            },
        )

        selected_entries = self.database.list_entries(
            match_ids=[matches[101]["id"], matches[102]["id"]],
            user_id=user_id,
        )
        session_entries = self.database.list_entries(
            match_ids=[matches[101]["id"], matches[102]["id"]],
            user_id=user_id,
            entry_type="Session",
            session="Morning",
        )
        self.assertEqual(len(selected_entries), 2)
        self.assertEqual(len(session_entries), 1)
        self.assertEqual(session_entries[0]["runs"], "7")
        self.assertEqual(session_entries[0]["support"], "")
        self.assertEqual(
            len(self.database.list_entries(match_id=matches[102]["id"], book_no=2)),
            1,
        )

        default_books = self.database.list_books(int(matches[101]["id"]))
        self.assertEqual([row["book_no"] for row in default_books], [1])
        self.database.save_book(
            int(matches[101]["id"]), 2, "Mundi A", 1.5, True, False, True
        )
        self.database.set_book_closed(int(matches[101]["id"]), 2, True)
        book = self.database.get_book(int(matches[101]["id"]), 2)
        self.assertEqual(book["mundi"], "Mundi A")
        self.assertTrue(book["is_closed"])
        self.assertTrue(book["f8_enabled"])
        self.database.save_entry_session(int(matches[101]["id"]), "Night")
        self.assertEqual(
            self.database.list_entry_sessions(int(matches[101]["id"])), ["Night"]
        )

        actions = {(row["entity"], row["action"]) for row in self.database.list_logs()}
        self.assertIn(("match", "created"), actions)
        self.assertIn(("user", "created"), actions)
        self.assertIn(("entry", "created"), actions)
        self.assertIn(("book", "updated"), actions)
        self.assertIn(("book", "closed"), actions)

    def test_existing_database_migrates_entry_columns(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "legacy.sqlite3"
        connection = sqlite3.connect(legacy_path)
        connection.executescript(
            """
            CREATE TABLE matches (
                id INTEGER PRIMARY KEY,
                code INTEGER NOT NULL UNIQUE,
                match_date TEXT NOT NULL,
                comment TEXT NOT NULL,
                teams TEXT NOT NULL,
                result TEXT NOT NULL DEFAULT 'Undeclared',
                winner TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE entries (
                id INTEGER PRIMARY KEY,
                match_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                entry_date TEXT NOT NULL,
                entry_type TEXT NOT NULL,
                patti_number TEXT NOT NULL DEFAULT '',
                rate REAL NOT NULL,
                amount REAL NOT NULL,
                mode TEXT NOT NULL DEFAULT '',
                team TEXT NOT NULL DEFAULT '',
                session TEXT NOT NULL DEFAULT '',
                runs TEXT NOT NULL DEFAULT '',
                yes_no TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE books (
                id INTEGER PRIMARY KEY,
                match_id INTEGER NOT NULL,
                book_no INTEGER NOT NULL,
                is_closed INTEGER NOT NULL DEFAULT 0,
                mundi TEXT NOT NULL DEFAULT '',
                mundi_rate REAL NOT NULL DEFAULT 0,
                cutting_book INTEGER NOT NULL DEFAULT 0,
                dibba_book INTEGER NOT NULL DEFAULT 0,
                UNIQUE (match_id, book_no)
            );
            """
        )
        connection.close()

        migrated = Database(legacy_path)
        with migrated.connect() as connection:
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(entries)")
            }
            book_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(books)")
            }
        self.assertTrue({"book_no", "support", "charge"}.issubset(columns))
        self.assertIn("f8_enabled", book_columns)

    def test_deleting_match_removes_books_and_named_sessions(self) -> None:
        self.database.save_match(None, 101, "2026-11-14", "Match one", "Falcons, Hawks")
        match_id = int(self.database.list_matches()[0]["id"])
        self.database.list_books(match_id)
        self.database.save_entry_session(match_id, "Evening")

        self.database.delete_match(match_id)

        self.assertEqual(self.database.list_matches(), [])
        with self.database.connect() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM books WHERE match_id = ?", (match_id,)
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM entry_sessions WHERE match_id = ?",
                    (match_id,),
                ).fetchone()[0],
                0,
            )

    def test_settling_transactions_store_manual_balances_and_filters(self) -> None:
        self.database.set_settling_opening_balance("Alice", 500)
        self.database.save_settling_transaction(
            None,
            {
                "entry_date": "2026-11-14",
                "name": "Alice",
                "side": "NAAM",
                "amount": 100,
                "balance": 600,
                "charge": 2,
                "code": "101",
                "third_party": "North",
                "category": "Monday Final",
            },
        )
        self.database.save_settling_transaction(
            None,
            {
                "entry_date": "2026-11-15",
                "name": "Alice",
                "side": "JAMA",
                "amount": 20,
                "balance": 580,
                "category": "Regular",
            },
        )

        monday_rows = self.database.list_settling_transactions(
            name="alice", category="Monday Final"
        )
        self.assertEqual(len(monday_rows), 1)
        self.assertEqual(monday_rows[0]["side"], "NAAM")
        self.assertEqual(monday_rows[0]["balance"], 600)
        self.assertEqual(self.database.get_settling_opening_balance("ALICE"), 500)

        transaction_id = int(monday_rows[0]["id"])
        self.database.set_settling_tallied(transaction_id, True)
        self.assertEqual(
            len(self.database.list_settling_transactions(tallied=True)), 1
        )
        self.database.delete_settling_transaction(transaction_id)
        self.assertEqual(
            len(self.database.list_settling_transactions(name="Alice")), 1
        )
        with self.assertRaises(ValueError):
            self.database.save_settling_transaction(
                None,
                {
                    "entry_date": "2026-11-15",
                    "name": "Alice",
                    "side": "INVALID",
                    "amount": 1,
                    "balance": 1,
                },
            )

    def test_import_old_database_maps_records_and_blocks_repeat_import(self) -> None:
        source = Database(Path(self.temp_dir.name) / "old.sqlite3")
        source.save_match(None, 101, "2026-11-14", "Old match", "Falcons, Hawks")
        source_user_values = {
            field: 0 if field in {
                "limit_amount",
                "patti_match",
                "patti_session",
                "patti_meter",
                "session_commission",
                "match_commission",
                "match_commission_all",
                "match_dibba",
                "session_dibba",
                "show_dibba_user",
                "cutting_user",
                "dibba_account",
            } else ""
            for field in USER_FIELDS
        }
        source_user_values.update(name="Imported user", state_ref="North")
        source.save_user(None, source_user_values)
        source_match_id = int(source.list_matches()[0]["id"])
        source_user_id = int(source.list_users()[0]["id"])
        source.save_entry(
            None,
            {
                "match_id": source_match_id,
                "user_id": source_user_id,
                "entry_date": "2026-11-14",
                "entry_type": "Match",
                "patti_number": "123",
                "rate": 2,
                "amount": 100,
                "mode": "K",
                "team": "Falcons",
                "session": "",
                "runs": "",
                "yes_no": "",
                "support": "manual",
                "charge": 1,
            },
        )

        result = self.database.import_old_database(source.path)

        self.assertEqual(result, {"matches": 1, "users": 1, "entries": 1})
        self.assertEqual(len(self.database.list_matches()), 1)
        self.assertEqual(len(self.database.list_users()), 1)
        self.assertEqual(
            [row["name"] for row in self.database.list_state_refs()], ["North"]
        )
        imported_entries = self.database.list_entries()
        self.assertEqual(len(imported_entries), 1)
        self.assertEqual(imported_entries[0]["user_name"], "Imported user")
        with self.assertRaisesRegex(ValueError, "already been imported"):
            self.database.import_old_database(source.path)

    def test_backup_and_blank_data_keep_the_live_database_reopenable(self) -> None:
        self.database.save_match(None, 101, "2026-11-14", "Match", "A, B")
        backup_path = Path(self.temp_dir.name) / "backup.sqlite3"

        self.database.backup_to(backup_path)

        self.assertTrue(backup_path.exists())
        backup = Database(backup_path)
        self.assertEqual(len(backup.list_matches()), 1)
        self.database.clear_application_data()
        self.assertEqual(self.database.list_matches(), [])
        self.assertEqual(self.database.list_users(), [])
        self.assertEqual(self.database.list_state_refs(), [])
        self.assertEqual(self.database.list_entries(), [])

    def test_failed_old_database_import_rolls_back_partial_records(self) -> None:
        source = Database(Path(self.temp_dir.name) / "invalid-old.sqlite3")
        source.save_match(None, 101, "2026-11-14", "Old match", "A, B")
        numeric_fields = {
            "limit_amount",
            "patti_match",
            "patti_session",
            "patti_meter",
            "session_commission",
            "match_commission",
            "match_commission_all",
            "match_dibba",
            "session_dibba",
            "show_dibba_user",
            "cutting_user",
            "dibba_account",
        }
        user_values = {
            field: 0 if field in numeric_fields else "" for field in USER_FIELDS
        }
        user_values.update(name="Invalid user", state_ref="North")
        source.save_user(None, user_values)
        with source.connect() as connection:
            connection.execute("UPDATE users SET name = ''")

        with self.assertRaisesRegex(ValueError, "has no name"):
            self.database.import_old_database(source.path)

        self.assertEqual(self.database.list_matches(), [])
        self.assertEqual(self.database.list_users(), [])
        with self.database.connect() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM imported_sources"
                ).fetchone()[0],
                0,
            )

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

    def test_numeric_entry_book_and_user_values_must_be_finite(self) -> None:
        self.database.save_match(None, 101, "2026-11-14", "Match", "A, B")
        match = self.database.list_matches()[0]
        user_id = self.create_user("Example user")
        entry = {
            "match_id": match["id"],
            "user_id": user_id,
            "entry_date": "2026-11-14",
            "entry_type": "Match",
            "rate": float("inf"),
            "amount": 100,
            "charge": 0,
            "team": "A",
        }

        with self.assertRaisesRegex(ValueError, "finite"):
            self.database.save_entry(None, entry)
        entry["rate"] = 1
        entry["amount"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            self.database.save_entry(None, entry)
        entry["amount"] = 100
        entry["charge"] = float("inf")
        with self.assertRaisesRegex(ValueError, "finite"):
            self.database.save_entry(None, entry)
        with self.assertRaisesRegex(ValueError, "finite"):
            self.database.save_book(int(match["id"]), 2, mundi_rate=float("nan"))

        user = self.database.list_users()[0]
        user_values = {field: user[field] for field in USER_FIELDS}
        user_values["limit_amount"] = float("inf")
        with self.assertRaisesRegex(ValueError, "finite"):
            self.database.save_user(user_id, user_values)

        self.assertEqual(self.database.list_entries(), [])
        with self.database.connect() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM books").fetchone()[0],
                0,
            )


if __name__ == "__main__":
    unittest.main()
