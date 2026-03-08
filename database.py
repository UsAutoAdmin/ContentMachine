"""
ContentMachine - Performance database for tracking video metrics.

Stores historical video performance (transcript, views, engagement rates)
to inform future scripting.
"""

import csv
import re
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent / "contentmachine.db"


def get_conn() -> sqlite3.Connection:
    """Get database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transcript TEXT NOT NULL,
                views INTEGER,
                skip_rate REAL,
                like_rate REAL,
                share_rate REAL,
                comment_rate REAL,
                save_rate REAL,
                retention_pct REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _parse_int(val: Any) -> int | None:
    """Parse integer, handling commas (e.g. 5,084) and empty strings."""
    if val is None or val == "":
        return None
    s = str(val).strip()
    if "," in s:
        parts = s.split(",")
        if len(parts) == 2 and parts[1].strip().isdigit() and len(parts[1].strip()) <= 3:
            s = "".join(parts)
        else:
            s = parts[0]
    s = s.replace(",", "")
    try:
        return int(float(s)) if s else None
    except (ValueError, TypeError):
        return None


def _parse_float(val: Any) -> float | None:
    """Parse float, handling empty strings."""
    if val is None or val == "":
        return None
    try:
        return float(str(val).strip().replace(",", ""))
    except (ValueError, TypeError):
        return None


def import_csv(path: Path) -> tuple[int, list[str]]:
    """
    Import videos from CSV. Returns (count_imported, list of errors).
    """
    init_db()
    conn = get_conn()
    imported = 0
    errors: list[str] = []

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                errors.append("Empty or invalid CSV")
                return 0, errors

            for i, row in enumerate(reader):
                try:
                    transcript = (row.get("Transcript") or "").strip()
                    if not transcript:
                        continue

                    views = _parse_int(row.get("Views"))
                    if views is not None and "," in str(row.get("Views", "")):
                        pass  # Already parsed

                    skip_rate = _parse_float(row.get("Skip Rate"))
                    if skip_rate is not None and skip_rate > 100:
                        skip_rate = None
                    conn.execute(
                        """
                        INSERT INTO videos (
                            transcript, views, skip_rate, like_rate, share_rate,
                            comment_rate, save_rate, retention_pct
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            transcript,
                            views,
                            skip_rate,
                            _parse_float(row.get("Like rate")),
                            _parse_float(row.get("Share Rate")),
                            _parse_float(row.get("Comment Rate")),
                            _parse_float(row.get("Save Rate")),
                            _parse_float(row.get("Retention % at end of video")),
                        ),
                    )
                    imported += 1
                except Exception as e:
                    errors.append(f"Row {i + 2}: {e}")
        conn.commit()
    except Exception as e:
        errors.append(str(e))
    finally:
        conn.close()

    return imported, errors


def list_videos(limit: int = 200, offset: int = 0, search: str = "") -> list[dict]:
    """List videos with optional search."""
    init_db()
    conn = get_conn()
    try:
        if search.strip():
            cur = conn.execute(
                """
                SELECT * FROM videos
                WHERE transcript LIKE ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (f"%{search.strip()}%", limit, offset),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM videos ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_video(video_id: int) -> dict | None:
    """Get a single video by ID."""
    init_db()
    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_video(video_id: int, data: dict) -> bool:
    """Update video metrics. Returns True if updated."""
    init_db()
    conn = get_conn()
    try:
        conn.execute(
            """
            UPDATE videos SET
                transcript = COALESCE(?, transcript),
                views = COALESCE(?, views),
                skip_rate = COALESCE(?, skip_rate),
                like_rate = COALESCE(?, like_rate),
                share_rate = COALESCE(?, share_rate),
                comment_rate = COALESCE(?, comment_rate),
                save_rate = COALESCE(?, save_rate),
                retention_pct = COALESCE(?, retention_pct),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                data.get("transcript"),
                data.get("views"),
                data.get("skip_rate"),
                data.get("like_rate"),
                data.get("share_rate"),
                data.get("comment_rate"),
                data.get("save_rate"),
                data.get("retention_pct"),
                video_id,
            ),
        )
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def add_video(data: dict) -> int:
    """Add a new video. Returns the new ID."""
    init_db()
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO videos (
                transcript, views, skip_rate, like_rate, share_rate,
                comment_rate, save_rate, retention_pct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("transcript", ""),
                data.get("views"),
                data.get("skip_rate"),
                data.get("like_rate"),
                data.get("share_rate"),
                data.get("comment_rate"),
                data.get("save_rate"),
                data.get("retention_pct"),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def delete_video(video_id: int) -> bool:
    """Delete a video. Returns True if deleted."""
    init_db()
    conn = get_conn()
    try:
        conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def reset_and_import_csv(path: Path) -> tuple[int, list[str]]:
    """Delete all videos and re-import from CSV. Returns (count, errors)."""
    init_db()
    conn = get_conn()
    try:
        conn.execute("DELETE FROM videos")
        conn.commit()
    finally:
        conn.close()
    return import_csv(path)


def get_stats() -> dict:
    """Get aggregate stats for analytics."""
    init_db()
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            SELECT
                COUNT(*) as total,
                AVG(views) as avg_views,
                AVG(skip_rate) as avg_skip_rate,
                AVG(like_rate) as avg_like_rate,
                AVG(retention_pct) as avg_retention
            FROM videos
            WHERE views IS NOT NULL
            """
        )
        row = cur.fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()
