import hashlib
import hmac
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


USER_FIELDS = (
    "name",
    "state_ref",
    "phone",
    "match_comm_1",
    "match_comm_2",
    "session_comm_1",
    "session_comm_2",
    "match_patti_1",
    "match_patti_2",
    "session_patti_1",
    "session_patti_2",
    "cutting_reference",
    "limit_mode",
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
)

ENTRY_FIELDS = (
    "match_id",
    "user_id",
    "entry_date",
    "entry_type",
    "patti_number",
    "rate",
    "amount",
    "mode",
    "team",
    "session",
    "runs",
    "yes_no",
)

PASSWORD_HASH_ITERATIONS = 600_000


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY,
                    code INTEGER NOT NULL UNIQUE,
                    match_date TEXT NOT NULL,
                    comment TEXT NOT NULL,
                    teams TEXT NOT NULL,
                    result TEXT NOT NULL DEFAULT 'Undeclared',
                    winner TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    state_ref TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '',
                    match_comm_1 TEXT NOT NULL DEFAULT '',
                    match_comm_2 TEXT NOT NULL DEFAULT '',
                    session_comm_1 TEXT NOT NULL DEFAULT '',
                    session_comm_2 TEXT NOT NULL DEFAULT '',
                    match_patti_1 TEXT NOT NULL DEFAULT '',
                    match_patti_2 TEXT NOT NULL DEFAULT '',
                    session_patti_1 TEXT NOT NULL DEFAULT '',
                    session_patti_2 TEXT NOT NULL DEFAULT '',
                    cutting_reference TEXT NOT NULL DEFAULT '',
                    limit_mode TEXT NOT NULL DEFAULT '',
                    limit_amount REAL NOT NULL DEFAULT 0,
                    patti_match REAL NOT NULL DEFAULT 0,
                    patti_session REAL NOT NULL DEFAULT 0,
                    patti_meter REAL NOT NULL DEFAULT 0,
                    session_commission REAL NOT NULL DEFAULT 0,
                    match_commission REAL NOT NULL DEFAULT 0,
                    match_commission_all INTEGER NOT NULL DEFAULT 0,
                    match_dibba INTEGER NOT NULL DEFAULT 0,
                    session_dibba INTEGER NOT NULL DEFAULT 0,
                    show_dibba_user INTEGER NOT NULL DEFAULT 0,
                    cutting_user INTEGER NOT NULL DEFAULT 0,
                    dibba_account INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY,
                    match_id INTEGER NOT NULL REFERENCES matches(id),
                    user_id INTEGER NOT NULL REFERENCES users(id),
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

                CREATE TABLE IF NOT EXISTS login_account (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    password_salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL
                );
                """
            )

    def has_login_account(self) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM login_account WHERE id = 1"
            ).fetchone()
        return row is not None

    def create_login_account(self, username: str, password: str) -> None:
        username = username.strip()
        if not username:
            raise ValueError("Enter a username.")
        if len(password) < 8:
            raise ValueError("Use a password with at least 8 characters.")
        salt = secrets.token_bytes(16)
        password_hash = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS
        )
        with self.connect() as connection:
            if connection.execute(
                "SELECT 1 FROM login_account WHERE id = 1"
            ).fetchone():
                raise ValueError("A login account already exists.")
            connection.execute(
                """
                INSERT INTO login_account
                    (id, username, password_salt, password_hash)
                VALUES (1, ?, ?, ?)
                """,
                (username, salt, password_hash),
            )

    def authenticate(self, username: str, password: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT username, password_salt, password_hash
                FROM login_account
                WHERE id = 1 AND username = ? COLLATE NOCASE
                """,
                (username.strip(),),
            ).fetchone()
        if row is None:
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            row["password_salt"],
            PASSWORD_HASH_ITERATIONS,
        )
        return hmac.compare_digest(candidate, row["password_hash"])

    def list_matches(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM matches ORDER BY match_date DESC, code DESC"
            ).fetchall()

    def save_match(
        self,
        match_id: int | None,
        code: int,
        match_date: str,
        comment: str,
        teams: str,
    ) -> None:
        with self.connect() as connection:
            if match_id is None:
                connection.execute(
                    """
                    INSERT INTO matches (code, match_date, comment, teams)
                    VALUES (?, ?, ?, ?)
                    """,
                    (code, match_date, comment, teams),
                )
            else:
                connection.execute(
                    """
                    UPDATE matches
                    SET code = ?, match_date = ?, comment = ?, teams = ?
                    WHERE id = ?
                    """,
                    (code, match_date, comment, teams, match_id),
                )

    def delete_match(self, match_id: int) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM matches WHERE id = ?", (match_id,))

    def next_match_code(self) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(code), 100) + 1 AS code FROM matches"
            ).fetchone()
            return int(row["code"])

    def list_users(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM users ORDER BY name COLLATE NOCASE"
            ).fetchall()

    def save_user(self, user_id: int | None, values: dict[str, Any]) -> None:
        columns = ", ".join(USER_FIELDS)
        placeholders = ", ".join("?" for _ in USER_FIELDS)
        field_values = [values[field] for field in USER_FIELDS]
        with self.connect() as connection:
            if user_id is None:
                connection.execute(
                    f"INSERT INTO users ({columns}) VALUES ({placeholders})",
                    field_values,
                )
            else:
                assignments = ", ".join(f"{field} = ?" for field in USER_FIELDS)
                connection.execute(
                    f"UPDATE users SET {assignments} WHERE id = ?",
                    field_values + [user_id],
                )

    def delete_user(self, user_id: int) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM users WHERE id = ?", (user_id,))

    def list_entries(
        self, match_id: int | None = None, user_id: int | None = None
    ) -> list[sqlite3.Row]:
        sql = """
            SELECT e.*, m.code AS match_code, m.comment AS match_comment,
                   u.name AS user_name
            FROM entries e
            JOIN matches m ON m.id = e.match_id
            JOIN users u ON u.id = e.user_id
        """
        clauses = []
        parameters: list[int] = []
        if match_id is not None:
            clauses.append("e.match_id = ?")
            parameters.append(match_id)
        if user_id is not None:
            clauses.append("e.user_id = ?")
            parameters.append(user_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY e.entry_date DESC, e.id DESC"
        with self.connect() as connection:
            return connection.execute(sql, parameters).fetchall()

    def save_entry(
        self, entry_id: int | None, values: dict[str, Any]
    ) -> None:
        columns = ", ".join(ENTRY_FIELDS)
        placeholders = ", ".join("?" for _ in ENTRY_FIELDS)
        field_values = [values[field] for field in ENTRY_FIELDS]
        with self.connect() as connection:
            if entry_id is None:
                connection.execute(
                    f"INSERT INTO entries ({columns}) VALUES ({placeholders})",
                    field_values,
                )
            else:
                assignments = ", ".join(f"{field} = ?" for field in ENTRY_FIELDS)
                connection.execute(
                    f"UPDATE entries SET {assignments} WHERE id = ?",
                    field_values + [entry_id],
                )

    def delete_entry(self, entry_id: int) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM entries WHERE id = ?", (entry_id,))

    def set_result(self, match_id: int, result: str, winner: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE matches SET result = ?, winner = ? WHERE id = ?",
                (result, winner if result == "Declared" else "", match_id),
            )

    def dashboard_metrics(self) -> dict[str, int | float]:
        with self.connect() as connection:
            matches = connection.execute(
                "SELECT COUNT(*) FROM matches WHERE result = 'Undeclared'"
            ).fetchone()[0]
            users = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            entries = connection.execute(
                "SELECT COUNT(*) FROM entries WHERE date(entry_date) = date('now', 'localtime')"
            ).fetchone()[0]
            amount = connection.execute(
                """
                SELECT COALESCE(SUM(amount), 0) FROM entries
                WHERE date(entry_date) = date('now', 'localtime')
                """
            ).fetchone()[0]
        return {
            "open_matches": int(matches),
            "users": int(users),
            "today_entries": int(entries),
            "today_amount": float(amount),
        }
