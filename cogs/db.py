import mysql.connector
import asyncio
from typing import Optional, Any, List, Dict
from . import config

class Database:
    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        self.loop = loop or asyncio.get_event_loop()

    def _get_conn(self):
        return mysql.connector.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            autocommit=True,
        )

    async def execute(self, query: str, params: Optional[tuple] = None) -> Optional[int]:
        """Execute a write query and return lastrowid when applicable (best-effort)."""
        def _exec() -> Optional[int]:
            conn = self._get_conn()
            cur = conn.cursor()
            try:
                cur.execute(query, params or ())
                conn.commit()
                lastrowid = cur.lastrowid
            finally:
                try:
                    cur.close()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass
            return lastrowid
        return await self.loop.run_in_executor(None, _exec)

    async def fetchall(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """Return rows as list[dict] where each dict maps column name to value."""
        def _run() -> List[Dict[str, Any]]:
            conn = self._get_conn()
            cur = conn.cursor()
            try:
                cur.execute(query, params or ())
                rows = cur.fetchall()
                cols = [c[0] for c in (cur.description or [])]
                results: List[Dict[str, Any]] = []
                for r in rows:
                    # r is a tuple; zip with cols to form dict
                    results.append(dict(zip(cols, r)))
            finally:
                try:
                    cur.close()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass
            return results
        return await self.loop.run_in_executor(None, _run)

    async def fetchone(self, query: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
        rows = await self.fetchall(query, params)
        return rows[0] if rows else None

    async def create_tables(self) -> None:
        q = """
        CREATE TABLE IF NOT EXISTS emergency_applications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            applicant_id BIGINT NOT NULL,
            applicant_mention VARCHAR(255),
            emergency TEXT,
            slots VARCHAR(64),
            info TEXT,
            staff_message_id BIGINT,
            posting_channel_id BIGINT,
            posting_message_id BIGINT,
            status VARCHAR(32) DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            approved_at DATETIME NULL,
            rejected_at DATETIME NULL,
            reason TEXT,
            staff_member_id BIGINT,
            deleted_at DATETIME NULL
        )
        """
        await self.execute(q)

    async def insert_application(self, applicant_id: int, applicant_mention: str, emergency: str, slots: str, info: str, staff_message_id: Optional[int] = None) -> Optional[int]:
        q = "INSERT INTO emergency_applications (applicant_id, applicant_mention, emergency, slots, info, staff_message_id) VALUES (%s,%s,%s,%s,%s,%s)"
        return await self.execute(q, (applicant_id, applicant_mention, emergency, slots, info, staff_message_id))

    async def update_staff_message_id(self, app_id: int, staff_message_id: int) -> None:
        q = "UPDATE emergency_applications SET staff_message_id=%s WHERE id=%s"
        await self.execute(q, (staff_message_id, app_id))

    async def accept_application(self, app_id: int, posting_channel_id: int, posting_message_id: int, staff_member_id: Optional[int]) -> None:
        q = "UPDATE emergency_applications SET status='accepted', posting_channel_id=%s, posting_message_id=%s, approved_at=NOW(), staff_member_id=%s WHERE id=%s"
        await self.execute(q, (posting_channel_id, posting_message_id, staff_member_id, app_id))

    async def reject_application(self, app_id: int, staff_member_id: Optional[int], reason: str) -> None:
        q = "UPDATE emergency_applications SET status='rejected', rejected_at=NOW(), reason=%s, staff_member_id=%s WHERE id=%s"
        await self.execute(q, (reason, staff_member_id, app_id))

    async def mark_deleted(self, app_id: int) -> None:
        q = "UPDATE emergency_applications SET status='expired', deleted_at=NOW() WHERE id=%s"
        await self.execute(q, (app_id,))

    async def find_expired_posts(self, days: int = 60) -> List[Dict[str, Any]]:
        q = "SELECT * FROM emergency_applications WHERE status='accepted' AND approved_at <= (NOW() - INTERVAL %s DAY) AND (deleted_at IS NULL)"
        return await self.fetchall(q, (days,))
