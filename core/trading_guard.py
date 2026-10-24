"""Neon-backed trading lock and persistent order intents."""

import uuid

from database import get_conn
from utils.logger import logger

LOCK_KEY = 240102026


def acquire_bot_lock():
    """PostgreSQL session lock: only one bot instance may trade."""
    conn = get_conn()
    try:
        conn.autocommit = True

        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_try_advisory_lock(%s) AS acquired",
                (LOCK_KEY,),
            )
            row = cur.fetchone()

        if not row or not row["acquired"]:
            conn.close()
            return None

        logger.info("Neon trading instance lock acquired")
        return conn

    except Exception:
        conn.close()
        raise


def assert_bot_lock(conn):
    """Fail closed if the lock-owning DB session is lost."""
    if conn is None or conn.closed:
        raise RuntimeError("Trading lock connection lost")

    with conn.cursor() as cur:
        cur.execute(
            '''
            SELECT EXISTS (
                SELECT 1 FROM pg_locks
                WHERE locktype = 'advisory'
                  AND pid = pg_backend_pid()
                  AND granted
                  AND classid = 0
                  AND objid = %s::oid
            ) AS held
            ''',
            (LOCK_KEY,),
        )
        row = cur.fetchone()

    if not row or row["held"] is not True:
        raise RuntimeError("Trading advisory lock no longer held")


def initialize_intents():
    sql = """
    CREATE TABLE IF NOT EXISTS trade_order_intents (
        link_id VARCHAR(36) PRIMARY KEY,
        symbol VARCHAR(20) NOT NULL,
        side VARCHAR(10) NOT NULL,
        status VARCHAR(24) NOT NULL DEFAULT 'PENDING',
        order_id VARCHAR(100),
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );

    CREATE UNIQUE INDEX IF NOT EXISTS
        idx_active_order_intent_symbol
    ON trade_order_intents (symbol)
    WHERE status IN (
        'PENDING', 'ACKNOWLEDGED',
        'UNCERTAIN', 'FILLED_UNSAVED'
    );
    """

    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql)
        logger.info("Order intent table ready")
    finally:
        conn.close()


def reserve_order(symbol, side):
    """
    Commit an intent BEFORE calling Bybit.
    Failure or timeout must not silently clear this reservation.
    """
    link_id = "bot-" + uuid.uuid4().hex[:28]

    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trade_order_intents
                        (link_id, symbol, side, status)
                    VALUES (%s, %s, %s, 'PENDING')
                    ON CONFLICT DO NOTHING
                    RETURNING link_id
                    """,
                    (link_id, symbol, side),
                )
                row = cur.fetchone()

        if not row:
            raise RuntimeError(
                f"{symbol}: unresolved order intent already exists"
            )

        return link_id
    finally:
        conn.close()


def mark_order(link_id, status, order_id=None):
    allowed = {
        "ACKNOWLEDGED",
        "UNCERTAIN",
        "FILLED_UNSAVED",
        "RECORDED",
    }
    if status not in allowed:
        raise ValueError("Unsupported intent status")

    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE trade_order_intents
                    SET status = %s,
                        order_id = COALESCE(%s, order_id),
                        updated_at = NOW()
                    WHERE link_id = %s
                    RETURNING link_id
                    """,
                    (status, order_id, link_id),
                )
                if cur.fetchone() is None:
                    raise RuntimeError("Order intent missing")
    finally:
        conn.close()


def pending_symbols():
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT symbol
                    FROM trade_order_intents
                    WHERE status IN (
                        'PENDING', 'ACKNOWLEDGED',
                        'UNCERTAIN', 'FILLED_UNSAVED'
                    )
                    """
                )
                return {r["symbol"] for r in cur.fetchall()}
    finally:
        conn.close()
