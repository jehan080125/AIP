import json
import aiosqlite
from pathlib import Path
from typing import Any, Optional

from backend.config import DATABASE_PATH
from backend.logging_config import get_logger

logger = get_logger(__name__)


class GameDatabase:
    def __init__(self, path: str = DATABASE_PATH):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS play_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    turn INTEGER,
                    event_type TEXT,
                    payload TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS save_slots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT DEFAULT 'default',
                    slot INTEGER DEFAULT 1,
                    session_snapshot TEXT,
                    episode_id TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.commit()
        logger.info("Database initialized at %s", self.path)

    async def log_event(
        self,
        session_id: str,
        turn: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO play_logs (session_id, turn, event_type, payload) VALUES (?, ?, ?, ?)",
                (session_id, turn, event_type, json.dumps(payload, ensure_ascii=False)),
            )
            await db.commit()

    async def save_slot(
        self,
        user_id: str,
        slot: int,
        episode_id: str,
        snapshot: dict[str, Any],
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO save_slots (user_id, slot, session_snapshot, episode_id)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, slot, json.dumps(snapshot, ensure_ascii=False), episode_id),
            )
            await db.commit()
