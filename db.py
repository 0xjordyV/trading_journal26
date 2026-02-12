import time
from typing import Optional

import aiosqlite


DEFAULT_DB_PATH = "trading_journal.db"


async def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                discord_id TEXT PRIMARY KEY,
                api_key TEXT NOT NULL,
                api_secret TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_discord_id TEXT NOT NULL,
                trade_id TEXT NOT NULL,
                symbol TEXT,
                timestamp_ms INTEGER,
                side TEXT,
                qty REAL,
                price REAL,
                realized_pnl REAL,
                fee REAL,
                note TEXT,
                raw_json TEXT,
                UNIQUE(user_discord_id, trade_id)
            )
            """
        )
        await db.commit()


async def upsert_user(
    discord_id: str,
    api_key: str,
    api_secret: str,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    now = int(time.time())
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO users (discord_id, api_key, api_secret, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET
                api_key=excluded.api_key,
                api_secret=excluded.api_secret,
                updated_at=excluded.updated_at
            """,
            (discord_id, api_key, api_secret, now, now),
        )
        await db.commit()


async def get_user(
    discord_id: str, db_path: str = DEFAULT_DB_PATH
) -> Optional[dict[str, str | int]]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT discord_id, api_key, api_secret, created_at, updated_at
            FROM users
            WHERE discord_id = ?
            """,
            (discord_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "discord_id": row["discord_id"],
        "api_key": row["api_key"],
        "api_secret": row["api_secret"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def delete_user(discord_id: str, db_path: str = DEFAULT_DB_PATH) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            DELETE FROM users
            WHERE discord_id = ?
            """,
            (discord_id,),
        )
        await db.commit()
