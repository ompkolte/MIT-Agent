from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import numpy as np
import orjson

from backend.answering.models.answer import GroundedAnswer
from backend.cache.models.cache_entry import CACHE_VERSION, CacheEntry


_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache_entries (
    cache_key TEXT PRIMARY KEY,
    normalized_query TEXT NOT NULL,
    original_query TEXT NOT NULL,
    answer_json BLOB NOT NULL,
    grounding_confidence REAL NOT NULL,
    hallucination_risk REAL NOT NULL,
    intent TEXT,
    primary_section_type TEXT,
    primary_page_type TEXT,
    cache_version TEXT NOT NULL,
    created_at REAL NOT NULL,
    last_used_at REAL NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0,
    embedding BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cache_section_type ON cache_entries(primary_section_type);
CREATE INDEX IF NOT EXISTS idx_cache_version ON cache_entries(cache_version);
CREATE INDEX IF NOT EXISTS idx_cache_created_at ON cache_entries(created_at);
"""


class CacheStore:
    """SQLite-backed persistence for the semantic cache. The in-memory EmbeddingIndex
    holds vectors for fast similarity lookup; this class is the source of truth for the
    full CacheEntry payload (answer JSON, metadata, stats)."""

    def __init__(self, db_path: Path | str = Path("datasets/semantic_cache.db")) -> None:
        self.db_path = Path(db_path) if not str(db_path).startswith(":") else db_path
        if isinstance(self.db_path, Path):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.db_path), check_same_thread=False, isolation_level=None
        )
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def upsert(
        self,
        cache_key: str,
        normalized_query: str,
        original_query: str,
        answer: GroundedAnswer,
        embedding: np.ndarray,
        intent: str | None = None,
        primary_section_type: str | None = None,
        primary_page_type: str | None = None,
    ) -> CacheEntry:
        now = time.time()
        embedding_blob = np.asarray(embedding, dtype=np.float32).tobytes()
        answer_json = orjson.dumps(answer.model_dump(mode="json"))
        self._conn.execute(
            """
            INSERT INTO cache_entries (
                cache_key, normalized_query, original_query, answer_json,
                grounding_confidence, hallucination_risk, intent,
                primary_section_type, primary_page_type, cache_version,
                created_at, last_used_at, hit_count, embedding
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                normalized_query = excluded.normalized_query,
                original_query = excluded.original_query,
                answer_json = excluded.answer_json,
                grounding_confidence = excluded.grounding_confidence,
                hallucination_risk = excluded.hallucination_risk,
                intent = excluded.intent,
                primary_section_type = excluded.primary_section_type,
                primary_page_type = excluded.primary_page_type,
                cache_version = excluded.cache_version,
                last_used_at = excluded.last_used_at,
                embedding = excluded.embedding
            """,
            (
                cache_key,
                normalized_query,
                original_query,
                answer_json,
                answer.confidence.grounding_confidence,
                answer.hallucination.hallucination_risk,
                intent,
                primary_section_type,
                primary_page_type,
                CACHE_VERSION,
                now,
                now,
                embedding_blob,
            ),
        )
        return self.get(cache_key)  # type: ignore[return-value]

    def get(self, cache_key: str) -> CacheEntry | None:
        row = self._conn.execute(
            "SELECT * FROM cache_entries WHERE cache_key = ?", (cache_key,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_entry(row)

    def get_embedding(self, cache_key: str) -> np.ndarray | None:
        row = self._conn.execute(
            "SELECT embedding FROM cache_entries WHERE cache_key = ?", (cache_key,)
        ).fetchone()
        if not row:
            return None
        return np.frombuffer(row[0], dtype=np.float32).copy()

    def all_entries(self) -> list[CacheEntry]:
        rows = self._conn.execute("SELECT * FROM cache_entries").fetchall()
        return [self._row_to_entry(row) for row in rows]

    def all_embeddings(self) -> list[tuple[str, np.ndarray]]:
        rows = self._conn.execute("SELECT cache_key, embedding FROM cache_entries").fetchall()
        return [(row[0], np.frombuffer(row[1], dtype=np.float32).copy()) for row in rows]

    def record_hit(self, cache_key: str) -> None:
        self._conn.execute(
            "UPDATE cache_entries SET hit_count = hit_count + 1, last_used_at = ? "
            "WHERE cache_key = ?",
            (time.time(), cache_key),
        )

    def delete(self, cache_key: str) -> bool:
        cur = self._conn.execute("DELETE FROM cache_entries WHERE cache_key = ?", (cache_key,))
        return cur.rowcount > 0

    def delete_where(
        self,
        cache_version: str | None = None,
        section_type: str | None = None,
        older_than: float | None = None,
    ) -> int:
        conditions: list[str] = []
        params: list = []
        if cache_version is not None:
            conditions.append("cache_version != ?")
            params.append(cache_version)
        if section_type is not None:
            conditions.append("primary_section_type = ?")
            params.append(section_type)
        if older_than is not None:
            conditions.append("created_at < ?")
            params.append(older_than)
        where = " AND ".join(conditions) if conditions else "1=1"
        cur = self._conn.execute(f"DELETE FROM cache_entries WHERE {where}", params)
        return cur.rowcount

    def clear(self) -> int:
        cur = self._conn.execute("DELETE FROM cache_entries")
        return cur.rowcount

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM cache_entries").fetchone()[0])

    def section_type_distribution(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT primary_section_type, COUNT(*) FROM cache_entries GROUP BY primary_section_type"
        ).fetchall()
        return {(s or "unknown"): int(c) for s, c in rows}

    @staticmethod
    def _row_to_entry(row) -> CacheEntry:
        (
            cache_key,
            normalized_query,
            original_query,
            answer_json,
            grounding,
            hallucination,
            intent,
            section_type,
            page_type,
            version,
            created_at,
            last_used_at,
            hit_count,
            _embedding,
        ) = row
        answer = GroundedAnswer.model_validate(orjson.loads(answer_json))
        return CacheEntry(
            cache_key=cache_key,
            normalized_query=normalized_query,
            original_query=original_query,
            answer=answer,
            grounding_confidence=float(grounding),
            hallucination_risk=float(hallucination),
            intent=intent,
            primary_section_type=section_type,
            primary_page_type=page_type,
            cache_version=version,
            created_at=float(created_at),
            last_used_at=float(last_used_at),
            hit_count=int(hit_count),
        )
