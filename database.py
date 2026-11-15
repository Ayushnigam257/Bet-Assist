import hashlib
import hmac
import json
import math
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence


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
    "book_no",
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
    "support",
    "charge",
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
                    book_no INTEGER NOT NULL DEFAULT 1,
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
                    support TEXT NOT NULL DEFAULT '',
                    charge REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY,
                    match_id INTEGER NOT NULL REFERENCES matches(id),
                    book_no INTEGER NOT NULL,
                    is_closed INTEGER NOT NULL DEFAULT 0,
                    mundi TEXT NOT NULL DEFAULT '',
                    mundi_rate REAL NOT NULL DEFAULT 0,
                    cutting_book INTEGER NOT NULL DEFAULT 0,
                    dibba_book INTEGER NOT NULL DEFAULT 0,
                    f8_enabled INTEGER NOT NULL DEFAULT 0,
                    UNIQUE (match_id, book_no)
                );

                CREATE TABLE IF NOT EXISTS entry_sessions (
                    id INTEGER PRIMARY KEY,
                    match_id INTEGER NOT NULL REFERENCES matches(id),
                    name TEXT NOT NULL,
                    UNIQUE (match_id, name)
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY,
                    entity TEXT NOT NULL,
                    entity_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS login_account (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    password_salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settling_balances (
                    name TEXT PRIMARY KEY COLLATE NOCASE,
                    opening_balance REAL NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS settling_transactions (
                    id INTEGER PRIMARY KEY,
                    entry_date TEXT NOT NULL,
                    name TEXT NOT NULL,
                    side TEXT NOT NULL CHECK (side IN ('NAAM', 'JAMA')),
                    amount REAL NOT NULL DEFAULT 0,
                    balance REAL NOT NULL DEFAULT 0,
                    charge REAL NOT NULL DEFAULT 0,
                    code TEXT NOT NULL DEFAULT '',
                    third_party TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT 'Regular',
                    tallied INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS imported_sources (
                    source_hash TEXT PRIMARY KEY,
                    source_name TEXT NOT NULL,
                    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            entry_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(entries)")
            }
            migrations = {
                "book_no": "INTEGER NOT NULL DEFAULT 1",
                "support": "TEXT NOT NULL DEFAULT ''",
                "charge": "REAL NOT NULL DEFAULT 0",
            }
            for column, definition in migrations.items():
                if column not in entry_columns:
                    connection.execute(
                        f"ALTER TABLE entries ADD COLUMN {column} {definition}"
                    )
            book_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(books)")
            }
            if "f8_enabled" not in book_columns:
                connection.execute(
                    "ALTER TABLE books ADD COLUMN f8_enabled INTEGER NOT NULL DEFAULT 0"
                )

    @staticmethod
    def _log(
        connection: sqlite3.Connection,
        entity: str,
        entity_id: int,
        action: str,
        details: Any,
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_log (entity, entity_id, action, details)
            VALUES (?, ?, ?, ?)
            """,
            (
                entity,
                entity_id,
                action,
                json.dumps(details, ensure_ascii=False, default=str),
            ),
        )

    def list_logs(
        self, entity: str | None = None, entity_id: int | None = None
    ) -> list[sqlite3.Row]:
        sql = "SELECT * FROM audit_log"
        clauses = []
        parameters: list[Any] = []
        if entity is not None:
            clauses.append("entity = ?")
            parameters.append(entity)
        if entity_id is not None:
            clauses.append("entity_id = ?")
            parameters.append(entity_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id DESC LIMIT 500"
        with self.connect() as connection:
            return connection.execute(sql, parameters).fetchall()

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
                cursor = connection.execute(
                    """
                    INSERT INTO matches (code, match_date, comment, teams)
                    VALUES (?, ?, ?, ?)
                    """,
                    (code, match_date, comment, teams),
                )
                match_id = int(cursor.lastrowid)
                action = "created"
            else:
                action = "updated"
                connection.execute(
                    """
                    UPDATE matches
                    SET code = ?, match_date = ?, comment = ?, teams = ?
                    WHERE id = ?
                    """,
                    (code, match_date, comment, teams, match_id),
                )
            self._log(
                connection,
                "match",
                match_id,
                action,
                {"code": code, "date": match_date, "comment": comment, "teams": teams},
            )

    def delete_match(self, match_id: int) -> None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT code, comment FROM matches WHERE id = ?", (match_id,)
            ).fetchone()
            connection.execute("DELETE FROM books WHERE match_id = ?", (match_id,))
            connection.execute(
                "DELETE FROM entry_sessions WHERE match_id = ?", (match_id,)
            )
            connection.execute("DELETE FROM matches WHERE id = ?", (match_id,))
            if row is not None:
                self._log(
                    connection,
                    "match",
                    match_id,
                    "deleted",
                    {"code": row["code"], "comment": row["comment"]},
                )

    def delete_matches(self, match_ids: Sequence[int]) -> None:
        with self.connect() as connection:
            for match_id in match_ids:
                row = connection.execute(
                    "SELECT code, comment FROM matches WHERE id = ?", (match_id,)
                ).fetchone()
                if row is None:
                    continue
                connection.execute("DELETE FROM books WHERE match_id = ?", (match_id,))
                connection.execute(
                    "DELETE FROM entry_sessions WHERE match_id = ?", (match_id,)
                )
                connection.execute("DELETE FROM matches WHERE id = ?", (match_id,))
                self._log(
                    connection,
                    "match",
                    int(match_id),
                    "deleted",
                    {"code": row["code"], "comment": row["comment"]},
                )

    def next_match_code(self) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(code), 100) + 1 AS code FROM matches"
            ).fetchone()
            return int(row["code"])

    def list_users(self, search: str = "") -> list[sqlite3.Row]:
        search = search.strip()
        with self.connect() as connection:
            if search:
                term = f"%{search}%"
                return connection.execute(
                    """
                    SELECT * FROM users
                    WHERE name LIKE ? COLLATE NOCASE
                       OR state_ref LIKE ? COLLATE NOCASE
                       OR phone LIKE ?
                    ORDER BY name COLLATE NOCASE
                    """,
                    (term, term, term),
                ).fetchall()
            return connection.execute(
                "SELECT * FROM users ORDER BY name COLLATE NOCASE"
            ).fetchall()

    def save_user(self, user_id: int | None, values: dict[str, Any]) -> None:
        numeric_fields = (
            "limit_amount",
            "patti_match",
            "patti_session",
            "patti_meter",
            "session_commission",
            "match_commission",
        )
        for field in numeric_fields:
            value = float(values[field])
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{field.replace('_', ' ').title()} must be a finite nonnegative number.")
        columns = ", ".join(USER_FIELDS)
        placeholders = ", ".join("?" for _ in USER_FIELDS)
        field_values = [values[field] for field in USER_FIELDS]
        with self.connect() as connection:
            if user_id is None:
                cursor = connection.execute(
                    f"INSERT INTO users ({columns}) VALUES ({placeholders})",
                    field_values,
                )
                user_id = int(cursor.lastrowid)
                action = "created"
            else:
                action = "updated"
                assignments = ", ".join(f"{field} = ?" for field in USER_FIELDS)
                connection.execute(
                    f"UPDATE users SET {assignments} WHERE id = ?",
                    field_values + [user_id],
                )
            self._log(
                connection,
                "user",
                user_id,
                action,
                {"name": values["name"], "state_ref": values["state_ref"]},
            )

    def delete_user(self, user_id: int) -> None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT name, state_ref FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
            if row is not None:
                self._log(
                    connection,
                    "user",
                    user_id,
                    "deleted",
                    {"name": row["name"], "state_ref": row["state_ref"]},
                )

    def delete_users(self, user_ids: Sequence[int]) -> None:
        with self.connect() as connection:
            for user_id in user_ids:
                row = connection.execute(
                    "SELECT name, state_ref FROM users WHERE id = ?", (user_id,)
                ).fetchone()
                if row is None:
                    continue
                connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
                self._log(
                    connection,
                    "user",
                    int(user_id),
                    "deleted",
                    {"name": row["name"], "state_ref": row["state_ref"]},
                )

    def list_entries(
        self,
        match_id: int | None = None,
        user_id: int | None = None,
        match_ids: Sequence[int] | None = None,
        entry_type: str | None = None,
        session: str | None = None,
        book_no: int | None = None,
    ) -> list[sqlite3.Row]:
        sql = """
            SELECT e.*, m.code AS match_code, m.comment AS match_comment,
                   m.match_date, m.result AS match_result,
                   u.name AS user_name, u.state_ref AS state_ref,
                   u.match_commission, u.session_commission
            FROM entries e
            JOIN matches m ON m.id = e.match_id
            JOIN users u ON u.id = e.user_id
        """
        clauses = []
        parameters: list[Any] = []
        if match_id is not None:
            clauses.append("e.match_id = ?")
            parameters.append(match_id)
        if user_id is not None:
            clauses.append("e.user_id = ?")
            parameters.append(user_id)
        if match_ids is not None:
            if match_ids:
                placeholders = ", ".join("?" for _ in match_ids)
                clauses.append(f"e.match_id IN ({placeholders})")
                parameters.extend(match_ids)
            else:
                clauses.append("0 = 1")
        if entry_type is not None:
            clauses.append("e.entry_type = ?")
            parameters.append(entry_type)
        if session is not None:
            clauses.append("e.session = ?")
            parameters.append(session)
        if book_no is not None:
            clauses.append("e.book_no = ?")
            parameters.append(book_no)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY e.entry_date DESC, e.id DESC"
        with self.connect() as connection:
            return connection.execute(sql, parameters).fetchall()

    def save_entry(
        self, entry_id: int | None, values: dict[str, Any]
    ) -> None:
        try:
            rate = float(values["rate"])
            amount = float(values["amount"])
            charge = float(values.get("charge", 0) or 0)
        except (TypeError, ValueError) as error:
            raise ValueError("Rate, amount, and CH must be numeric.") from error
        if not all(math.isfinite(value) for value in (rate, amount, charge)):
            raise ValueError("Rate, amount, and CH must be finite numbers.")
        if rate <= 0 or amount <= 0:
            raise ValueError("Rate and amount must be greater than zero.")
        if charge < 0:
            raise ValueError("CH cannot be negative.")
        columns = ", ".join(ENTRY_FIELDS)
        placeholders = ", ".join("?" for _ in ENTRY_FIELDS)
        defaults: dict[str, Any] = {"book_no": 1, "support": "", "charge": 0}
        field_values = [
            values.get(field, defaults.get(field, ""))
            for field in ENTRY_FIELDS
        ]
        with self.connect() as connection:
            if entry_id is None:
                cursor = connection.execute(
                    f"INSERT INTO entries ({columns}) VALUES ({placeholders})",
                    field_values,
                )
                entry_id = int(cursor.lastrowid)
                action = "created"
            else:
                action = "updated"
                assignments = ", ".join(f"{field} = ?" for field in ENTRY_FIELDS)
                connection.execute(
                    f"UPDATE entries SET {assignments} WHERE id = ?",
                    field_values + [entry_id],
                )
            self._log(
                connection,
                "entry",
                entry_id,
                action,
                {field: values.get(field, defaults.get(field, "")) for field in ENTRY_FIELDS},
            )

    def delete_entry(self, entry_id: int) -> None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT match_id, user_id, entry_date, entry_type, amount
                FROM entries WHERE id = ?
                """,
                (entry_id,),
            ).fetchone()
            connection.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
            if row is not None:
                self._log(
                    connection,
                    "entry",
                    entry_id,
                    "deleted",
                    dict(row),
                )

    def list_books(self, match_id: int) -> list[sqlite3.Row]:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO books (match_id, book_no) VALUES (?, 1)",
                (match_id,),
            )
            return connection.execute(
                "SELECT * FROM books WHERE match_id = ? ORDER BY book_no",
                (match_id,),
            ).fetchall()

    def save_book(
        self,
        match_id: int,
        book_no: int,
        mundi: str = "",
        mundi_rate: float = 0,
        cutting_book: bool = False,
        dibba_book: bool = False,
        f8_enabled: bool = False,
    ) -> None:
        mundi_rate = float(mundi_rate)
        if not math.isfinite(mundi_rate) or mundi_rate < 0:
            raise ValueError("Mundi rate must be a finite nonnegative number.")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO books
                    (match_id, book_no, mundi, mundi_rate, cutting_book, dibba_book, f8_enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(match_id, book_no) DO UPDATE SET
                    mundi = excluded.mundi,
                    mundi_rate = excluded.mundi_rate,
                    cutting_book = excluded.cutting_book,
                    dibba_book = excluded.dibba_book,
                    f8_enabled = excluded.f8_enabled
                """,
                (
                    match_id,
                    book_no,
                    mundi,
                    mundi_rate,
                    int(cutting_book),
                    int(dibba_book),
                    int(f8_enabled),
                ),
            )
            self._log(
                connection,
                "book",
                match_id,
                "updated",
                {
                    "book_no": book_no,
                    "mundi": mundi,
                    "mundi_rate": mundi_rate,
                    "cutting_book": cutting_book,
                    "dibba_book": dibba_book,
                    "f8_enabled": f8_enabled,
                },
            )

    def set_book_closed(self, match_id: int, book_no: int, closed: bool) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO books (match_id, book_no, is_closed)
                VALUES (?, ?, ?)
                ON CONFLICT(match_id, book_no) DO UPDATE SET
                    is_closed = excluded.is_closed
                """,
                (match_id, book_no, int(closed)),
            )
            self._log(
                connection,
                "book",
                match_id,
                "closed" if closed else "opened",
                {"book_no": book_no},
            )

    def get_book(self, match_id: int, book_no: int) -> sqlite3.Row:
        self.list_books(match_id)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM books WHERE match_id = ? AND book_no = ?",
                (match_id, book_no),
            ).fetchone()
        if row is None:
            raise LookupError(f"Book {book_no} does not exist for match {match_id}.")
        return row

    def list_entry_sessions(self, match_id: int) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT name FROM entry_sessions WHERE match_id = ?
                UNION
                SELECT DISTINCT session AS name
                FROM entries
                WHERE match_id = ? AND session <> ''
                ORDER BY name COLLATE NOCASE
                """,
                (match_id, match_id),
            ).fetchall()
        return [str(row["name"]) for row in rows]

    def save_entry_session(self, match_id: int, name: str) -> None:
        name = name.strip()
        if not name:
            raise ValueError("Enter a session name.")
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO entry_sessions (match_id, name) VALUES (?, ?)",
                (match_id, name),
            )
            if cursor.rowcount:
                row = connection.execute(
                    "SELECT id FROM entry_sessions WHERE match_id = ? AND name = ?",
                    (match_id, name),
                ).fetchone()
                self._log(
                    connection,
                    "entry_session",
                    int(row["id"]),
                    "created",
                    {"match_id": match_id, "name": name},
                )

    def set_result(self, match_id: int, result: str, winner: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE matches SET result = ?, winner = ? WHERE id = ?",
                (result, winner if result == "Declared" else "", match_id),
            )
            self._log(
                connection,
                "match",
                match_id,
                "result_changed",
                {"result": result, "winner": winner if result == "Declared" else ""},
            )

    def list_settling_transactions(
        self,
        name: str | None = None,
        category: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        tallied: bool | None = None,
    ) -> list[sqlite3.Row]:
        sql = "SELECT * FROM settling_transactions"
        clauses = []
        parameters: list[Any] = []
        if name is not None:
            clauses.append("name = ? COLLATE NOCASE")
            parameters.append(name)
        if category is not None:
            clauses.append("category = ?")
            parameters.append(category)
        if start_date is not None:
            clauses.append("entry_date >= ?")
            parameters.append(start_date)
        if end_date is not None:
            clauses.append("entry_date <= ?")
            parameters.append(end_date)
        if tallied is not None:
            clauses.append("tallied = ?")
            parameters.append(int(tallied))
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY entry_date DESC, id DESC"
        with self.connect() as connection:
            return connection.execute(sql, parameters).fetchall()

    def save_settling_transaction(
        self, transaction_id: int | None, values: dict[str, Any]
    ) -> None:
        side = str(values["side"]).upper()
        category = str(values.get("category", "Regular"))
        if side not in {"NAAM", "JAMA"}:
            raise ValueError("Settlement side must be NAAM or JAMA.")
        if category not in {"Regular", "Monday Final"}:
            raise ValueError("Unknown settlement category.")
        fields = (
            str(values["entry_date"]),
            str(values["name"]).strip(),
            side,
            float(values["amount"]),
            float(values["balance"]),
            float(values.get("charge", 0)),
            str(values.get("code", "")).strip(),
            str(values.get("third_party", "")).strip(),
            category,
        )
        if not fields[1]:
            raise ValueError("A settlement name is required.")
        with self.connect() as connection:
            if transaction_id is None:
                cursor = connection.execute(
                    """
                    INSERT INTO settling_transactions
                        (entry_date, name, side, amount, balance, charge,
                         code, third_party, category)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    fields,
                )
                saved_id = int(cursor.lastrowid)
                self._log(
                    connection,
                    "settling_transaction",
                    saved_id,
                    "created",
                    {"date": fields[0], "name": fields[1], "side": side},
                )
            else:
                connection.execute(
                    """
                    UPDATE settling_transactions
                    SET entry_date = ?, name = ?, side = ?, amount = ?,
                        balance = ?, charge = ?, code = ?, third_party = ?,
                        category = ?
                    WHERE id = ?
                    """,
                    (*fields, transaction_id),
                )
                self._log(
                    connection,
                    "settling_transaction",
                    transaction_id,
                    "updated",
                    {"date": fields[0], "name": fields[1], "side": side},
                )

    def delete_settling_transaction(self, transaction_id: int) -> None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT name FROM settling_transactions WHERE id = ?",
                (transaction_id,),
            ).fetchone()
            connection.execute(
                "DELETE FROM settling_transactions WHERE id = ?",
                (transaction_id,),
            )
            if row is not None:
                self._log(
                    connection,
                    "settling_transaction",
                    transaction_id,
                    "deleted",
                    {"name": row["name"]},
                )

    def set_settling_opening_balance(self, name: str, amount: float) -> None:
        if not name.strip():
            raise ValueError("A settlement name is required.")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO settling_balances (name, opening_balance)
                VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET opening_balance = excluded.opening_balance
                """,
                (name.strip(), float(amount)),
            )

    def get_settling_opening_balance(self, name: str) -> float:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT opening_balance FROM settling_balances WHERE name = ? COLLATE NOCASE",
                (name,),
            ).fetchone()
        return 0.0 if row is None else float(row["opening_balance"])

    def set_settling_tallied(self, transaction_id: int, tallied: bool) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE settling_transactions SET tallied = ? WHERE id = ?",
                (int(tallied), transaction_id),
            )

    def backup_to(self, target_path: str | Path) -> None:
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.resolve() == Path(self.path).resolve():
            raise ValueError("The backup path must differ from the live database.")
        source = sqlite3.connect(self.path)
        try:
            backup = sqlite3.connect(str(target))
            try:
                source.backup(backup)
            finally:
                backup.close()
        finally:
            source.close()

    def import_old_database(self, source_path: str | Path) -> dict[str, int]:
        source_file = Path(source_path)
        if not source_file.is_file():
            raise FileNotFoundError(source_file)
        if source_file.resolve() == Path(self.path).resolve():
            raise ValueError("Choose a database other than the current database.")
        digest = hashlib.sha256()
        with source_file.open("rb") as source_stream:
            for block in iter(lambda: source_stream.read(1024 * 1024), b""):
                digest.update(block)
        source_hash = digest.hexdigest()
        source = sqlite3.connect(str(source_file))
        source.row_factory = sqlite3.Row
        try:
            source_tables = {
                row["name"]
                for row in source.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            if not {"matches", "users", "entries"}.issubset(source_tables):
                raise ValueError(
                    "The selected file is not a compatible Betting Assistant database."
                )
            match_rows = source.execute("SELECT * FROM matches").fetchall()
            user_rows = source.execute("SELECT * FROM users").fetchall()
            entry_rows = source.execute("SELECT * FROM entries").fetchall()
            required_entry_fields = {
                "match_id",
                "user_id",
                "entry_date",
                "entry_type",
                "rate",
                "amount",
            }
            if entry_rows and not required_entry_fields.issubset(
                set(entry_rows[0].keys())
            ):
                raise ValueError(
                    "The old database entries table is missing required fields."
                )

            imported = {"matches": 0, "users": 0, "entries": 0}
            with self.connect() as target:
                if target.execute(
                    "SELECT 1 FROM imported_sources WHERE source_hash = ?",
                    (source_hash,),
                ).fetchone():
                    raise ValueError("This database has already been imported.")

                target_matches = {
                    int(row["code"]): int(row["id"])
                    for row in target.execute("SELECT id, code FROM matches")
                }
                match_ids: dict[int, int] = {}
                for row in match_rows:
                    old_id = int(row["id"])
                    code = int(row["code"])
                    match_id = target_matches.get(code)
                    if match_id is None:
                        result = str(row["result"]) if "result" in row.keys() else "Undeclared"
                        if result not in {"Declared", "Undeclared"}:
                            result = "Undeclared"
                        winner = str(row["winner"]) if "winner" in row.keys() else ""
                        if result != "Declared":
                            winner = ""
                        cursor = target.execute(
                            """
                            INSERT INTO matches
                                (code, match_date, comment, teams, result, winner)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                code,
                                str(row["match_date"]),
                                str(row["comment"]),
                                str(row["teams"]),
                                result,
                                winner,
                            ),
                        )
                        match_id = int(cursor.lastrowid)
                        target_matches[code] = match_id
                        imported["matches"] += 1
                    match_ids[old_id] = match_id

                target_users = target.execute(
                    "SELECT * FROM users"
                ).fetchall()
                def user_key(row: sqlite3.Row | dict[str, Any]) -> tuple[str, str, str]:
                    return (
                        str(row["name"] or "").strip().casefold(),
                        str(row["state_ref"] or "").strip().casefold(),
                        str(row["phone"] or "").strip(),
                    )

                users_by_key = {user_key(row): int(row["id"]) for row in target_users}
                numeric_user_fields = {
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
                user_ids: dict[int, int] = {}
                user_columns = ", ".join(USER_FIELDS)
                user_placeholders = ", ".join("?" for _ in USER_FIELDS)
                for row in user_rows:
                    old_id = int(row["id"])
                    values = {
                        field: (
                            row[field]
                            if field in row.keys() and row[field] is not None
                            else (0 if field in numeric_user_fields else "")
                        )
                        for field in USER_FIELDS
                    }
                    if not str(values["name"]).strip():
                        raise ValueError("An old database user has no name.")
                    key = user_key(values)
                    user_id = users_by_key.get(key)
                    if user_id is None:
                        cursor = target.execute(
                            f"INSERT INTO users ({user_columns}) VALUES ({user_placeholders})",
                            tuple(values[field] for field in USER_FIELDS),
                        )
                        user_id = int(cursor.lastrowid)
                        users_by_key[key] = user_id
                        imported["users"] += 1
                    user_ids[old_id] = user_id

                entry_columns = ", ".join(ENTRY_FIELDS)
                entry_placeholders = ", ".join("?" for _ in ENTRY_FIELDS)
                entry_defaults: dict[str, Any] = {
                    "book_no": 1,
                    "patti_number": "",
                    "mode": "",
                    "team": "",
                    "session": "",
                    "runs": "",
                    "yes_no": "",
                    "support": "",
                    "charge": 0,
                }
                for row in entry_rows:
                    old_match_id = int(row["match_id"])
                    old_user_id = int(row["user_id"])
                    if old_match_id not in match_ids or old_user_id not in user_ids:
                        continue
                    values = {
                        field: row[field]
                        if field in row.keys() and row[field] is not None
                        else entry_defaults.get(field, "")
                        for field in ENTRY_FIELDS
                    }
                    values["match_id"] = match_ids[old_match_id]
                    values["user_id"] = user_ids[old_user_id]
                    target.execute(
                        f"INSERT INTO entries ({entry_columns}) VALUES ({entry_placeholders})",
                        tuple(values[field] for field in ENTRY_FIELDS),
                    )
                    imported["entries"] += 1

                for row in source.execute(
                    "SELECT * FROM books"
                ).fetchall() if "books" in source_tables else ():
                    old_match_id = int(row["match_id"])
                    if old_match_id not in match_ids:
                        continue
                    book_fields = (
                        "book_no",
                        "is_closed",
                        "mundi",
                        "mundi_rate",
                        "cutting_book",
                        "dibba_book",
                        "f8_enabled",
                    )
                    values = [
                        row[field] if field in row.keys() else 0
                        for field in book_fields
                    ]
                    target.execute(
                        """
                        INSERT OR IGNORE INTO books
                            (match_id, book_no, is_closed, mundi, mundi_rate,
                             cutting_book, dibba_book, f8_enabled)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (match_ids[old_match_id], *values),
                    )
                if "entry_sessions" in source_tables:
                    for row in source.execute("SELECT * FROM entry_sessions"):
                        old_match_id = int(row["match_id"])
                        if old_match_id in match_ids:
                            target.execute(
                                "INSERT OR IGNORE INTO entry_sessions (match_id, name) VALUES (?, ?)",
                                (match_ids[old_match_id], row["name"]),
                            )
                target.execute(
                    "INSERT INTO imported_sources (source_hash, source_name) VALUES (?, ?)",
                    (source_hash, source_file.name),
                )
            return imported
        finally:
            source.close()

    def clear_application_data(self) -> None:
        with self.connect() as connection:
            for table in (
                "entries",
                "books",
                "entry_sessions",
                "settling_transactions",
                "settling_balances",
                "matches",
                "users",
                "audit_log",
                "imported_sources",
            ):
                connection.execute(f"DELETE FROM {table}")

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
