
"""Read-only data for the existing dashboard."""
from fastapi import APIRouter, HTTPException
from config.settings import API_KEY, API_SECRET, DEMO_MODE, TESTNET
from database import get_conn
from utils.logger import logger

router = APIRouter()


@router.get("/api/real_balance")
def real_balance():
    try:
        from pybit.unified_trading import HTTP

        session = HTTP(
            testnet=TESTNET,
            demo=DEMO_MODE,
            api_key=API_KEY,
            api_secret=API_SECRET,
        )
        response = session.get_wallet_balance(
            accountType="UNIFIED"
        )

        if response.get("retCode") != 0:
            raise RuntimeError(
                str(response.get("retMsg", "Bybit error"))
            )

        accounts = response.get("result", {}).get("list", [])
        if not accounts:
            raise RuntimeError("No account data returned")

        equity = accounts[0].get("totalEquity")
        if equity is None:
            raise RuntimeError("Account equity unavailable")

        return {
            "balance": float(equity),
            "currency": "USD",
            "source": "Bybit Demo Unified",
        }

    except Exception as exc:
        logger.error(f"Dashboard balance error: {exc}")
        raise HTTPException(
            status_code=503,
            detail="Bybit demo balance unavailable",
        )


@router.get("/api/daily_stats")
def daily_stats():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                      COUNT(*) AS total,
                      COUNT(*) FILTER (
                        WHERE side = 'Buy'
                      ) AS buys,
                      COUNT(*) FILTER (
                        WHERE side = 'Sell'
                      ) AS sells,
                      COUNT(*) FILTER (
                        WHERE status = 'WIN'
                      ) AS wins,
                      COUNT(*) FILTER (
                        WHERE status = 'LOSS'
                      ) AS losses,
                      COALESCE(
                        SUM(pnl) FILTER (
                          WHERE status IN ('WIN','LOSS')
                        ), 0
                      ) AS net_pnl
                    FROM trades
                    WHERE time >= CURRENT_DATE
                      AND time < CURRENT_DATE + INTERVAL '1 day'
                """)
                row = cur.fetchone()

        return {
            "total": int(row["total"]),
            "buys": int(row["buys"]),
            "sells": int(row["sells"]),
            "wins": int(row["wins"]),
            "losses": int(row["losses"]),
            "net_pnl": float(row["net_pnl"]),
            "basis": "trade_entry_date",
        }

    except Exception as exc:
        logger.error(f"Dashboard daily stats error: {exc}")
        raise HTTPException(
            status_code=503,
            detail="Neon daily statistics unavailable",
        )
