from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash


USERNAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{2,31}$")


@dataclass(frozen=True)
class User:
    id: int
    username: str
    is_admin: bool
    created_utc: str

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "is_admin": self.is_admin,
            "created_utc": self.created_utc,
        }


class AuthStore:
    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    password_hash TEXT NOT NULL,
                    is_admin INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1)),
                    created_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS job_owners (
                    job_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_utc TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS job_owners_user_id_idx ON job_owners(user_id);
                """
            )

    @staticmethod
    def validate_username(username: str) -> str:
        normalized = username.strip()
        if not USERNAME_RE.fullmatch(normalized):
            raise ValueError("username must be 3-32 characters using letters, numbers, dot, dash, or underscore")
        return normalized

    @staticmethod
    def validate_password(password: str) -> None:
        if len(password) < 8:
            raise ValueError("password must be at least 8 characters")
        if len(password) > 128:
            raise ValueError("password must be 128 characters or fewer")

    @staticmethod
    def _user_from_row(row: sqlite3.Row | None) -> User | None:
        if row is None:
            return None
        return User(
            id=int(row["id"]),
            username=str(row["username"]),
            is_admin=bool(row["is_admin"]),
            created_utc=str(row["created_utc"]),
        )

    def create_user(self, username: str, password: str, created_utc: str, *, is_admin: bool = False) -> User:
        normalized = self.validate_username(username)
        self.validate_password(password)
        password_hash = generate_password_hash(password, method="scrypt")
        try:
            with closing(self._connect()) as connection, connection:
                cursor = connection.execute(
                    "INSERT INTO users (username, password_hash, is_admin, created_utc) VALUES (?, ?, ?, ?)",
                    (normalized, password_hash, int(is_admin), created_utc),
                )
                user_id = int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise ValueError("that username is already registered") from exc
        user = self.get_user(user_id)
        if user is None:
            raise RuntimeError("created user could not be read back")
        return user

    def upsert_admin(self, username: str, password: str, created_utc: str) -> User:
        normalized = self.validate_username(username)
        self.validate_password(password)
        password_hash = generate_password_hash(password, method="scrypt")
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO users (username, password_hash, is_admin, created_utc)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash, is_admin = 1
                """,
                (normalized, password_hash, created_utc),
            )
            row = connection.execute(
                "SELECT id, username, is_admin, created_utc FROM users WHERE username = ? COLLATE NOCASE",
                (normalized,),
            ).fetchone()
        user = self._user_from_row(row)
        if user is None:
            raise RuntimeError("admin account could not be read back")
        return user

    def authenticate(self, username: str, password: str) -> User | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT id, username, password_hash, is_admin, created_utc FROM users WHERE username = ? COLLATE NOCASE",
                (username.strip(),),
            ).fetchone()
        if row is None or not check_password_hash(str(row["password_hash"]), password):
            return None
        return self._user_from_row(row)

    def get_user(self, user_id: int) -> User | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT id, username, is_admin, created_utc FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return self._user_from_row(row)

    def assign_job(self, user_id: int, job_id: str, created_utc: str) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO job_owners (job_id, user_id, created_utc) VALUES (?, ?, ?)",
                (job_id, user_id, created_utc),
            )

    def assign_unowned_jobs(self, user_id: int, job_ids: list[str], created_utc: str) -> int:
        added = 0
        with closing(self._connect()) as connection, connection:
            for job_id in job_ids:
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO job_owners (job_id, user_id, created_utc) VALUES (?, ?, ?)",
                    (job_id, user_id, created_utc),
                )
                added += cursor.rowcount
        return added

    def job_ids_for_user(self, user_id: int) -> set[str]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute("SELECT job_id FROM job_owners WHERE user_id = ?", (user_id,)).fetchall()
        return {str(row["job_id"]) for row in rows}

    def user_owns_job(self, user_id: int, job_id: str) -> bool:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT 1 FROM job_owners WHERE user_id = ? AND job_id = ?",
                (user_id, job_id),
            ).fetchone()
        return row is not None
