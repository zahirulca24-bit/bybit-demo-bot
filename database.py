import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from utils.logger import logger

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")


def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db():
    """Create tables if not exist."""
    sql = """
    CREATE TABLE IF NOT EXISTS trades (
        id          SERIAL PRIMARY KEY,
        time        TIMESTAMP NOT NULL,
        symbol      VARCHAR(20) NOT NULL,
        side        VARCHAR(10) NOT NULL,
        entry_price NUMERIC(20,8) NOT NULL,
        qty         NUMERIC(20,8) NOT NULL,
        stop_loss   NUMERIC(20,8),
        take_profit NUMERIC(20,8),
        exit_price  NUMERIC(20,8),
        pnl         NUMERIC(20,8),
        status      VARCHAR(20) DEFAULT 'OPEN',
        order_id    VARCHAR(100)
    );

    CREATE TABLE IF NOT EXISTS journal (
        id           SERIAL PRIMARY KEY,
        date         DATE NOT NULL,
        total_trades INT DEFAULT 0,
        wins         INT DEFAULT 0,
        losses       INT DEFAULT 0,
        total_pnl    NUMERIC(20,4) DEFAULT 0,
        best_trade   NUMERIC(20,4) DEFAULT 0,
        worst_trade  NUMERIC(20,4) DEFAULT 0,
        updated_at   TIMESTAMP DEFAULT NOW()
    );
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
        logger.info("Database tables ready")
    except Exception as e:
        logger.error(f"Database init error: {e}")


def insert_trade(symbol, side, entry_price, qty, stop_loss, take_profit, order_id=""):
    sql = """
    INSERT INTO trades (time, symbol, side, entry_price, qty, stop_loss, take_profit, order_id, status)
    VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, 'OPEN')
    RETURNING id;
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (symbol, side, entry_price, qty, stop_loss, take_profit, order_id))
                trade_id = cur.fetchone()["id"]
            conn.commit()
        logger.info(f"[DB] Trade inserted id={trade_id} {symbol} {side}")
        return trade_id
    except Exception as e:
        logger.error(f"[DB] insert_trade error: {e}")
        return None


def close_trade(trade_id, exit_price, pnl):
    sql = """
    UPDATE trades
    SET exit_price=%s, pnl=%s, status=%s
    WHERE id=%s;
    """
    status = "WIN" if pnl > 0 else "LOSS"
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (exit_price, pnl, status, trade_id))
            conn.commit()
        logger.info(f"[DB] Trade closed id={trade_id} pnl={pnl} status={status}")
    except Exception as e:
        logger.error(f"[DB] close_trade error: {e}")


def get_all_trades(limit=50):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM trades ORDER BY time DESC LIMIT %s;", (limit,)
                )
                return cur.fetchall()
    except Exception as e:
        logger.error(f"[DB] get_all_trades error: {e}")
        return []


def get_journal_stats():
    sql = """
    SELECT
        COUNT(*)                          AS total_trades,
        COUNT(*) FILTER (WHERE status='WIN')  AS wins,
        COUNT(*) FILTER (WHERE status='LOSS') AS losses,
        COALESCE(SUM(pnl), 0)             AS total_pnl,
        COALESCE(MAX(pnl), 0)             AS best_trade,
        COALESCE(MIN(pnl), 0)             AS worst_trade,
        COALESCE(AVG(pnl), 0)             AS avg_pnl
    FROM trades
    WHERE status IN ('WIN','LOSS');
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return dict(cur.fetchone())
    except Exception as e:
        logger.error(f"[DB] get_journal_stats error: {e}")
        return {}


def get_symbol_stats():
    sql = """
    SELECT
        symbol,
        COUNT(*) AS trades,
        COUNT(*) FILTER (WHERE status='WIN') AS wins,
        COALESCE(SUM(pnl),0) AS total_pnl
    FROM trades
    WHERE status IN ('WIN','LOSS')
    GROUP BY symbol
    ORDER BY total_pnl DESC;
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"[DB] get_symbol_stats error: {e}")
        return []