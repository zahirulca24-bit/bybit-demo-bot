
"""Recover only orders already safely recorded in Neon.

Never place orders, close positions, or invent missing trade records.
Uncertain intents remain blocked.
"""

from decimal import Decimal

from pybit.unified_trading import HTTP
from config.settings import (
    API_KEY, API_SECRET, DEMO_MODE, TESTNET,
)
from database import get_conn
from core.trading_guard import mark_order
from utils.logger import logger


ACTIVE = (
    "PENDING",
    "ACKNOWLEDGED",
    "UNCERTAIN",
    "FILLED_UNSAVED",
)


def load_pending():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT link_id, symbol, side, status, order_id
                FROM trade_order_intents
                WHERE status = ANY(%s)
                ORDER BY created_at
            """, (list(ACTIVE),))
            return [dict(row) for row in cur.fetchall()]


def find_saved_order(order_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, symbol, side, qty, order_id
                FROM trades
                WHERE order_id = %s
            """, (order_id,))
            return [dict(row) for row in cur.fetchall()]


def verify_recorded_intent(session, intent):
    """Return confirmed Bybit order ID, otherwise None."""
    response = session.get_order_history(
        category="linear",
        symbol=intent["symbol"],
        orderLinkId=intent["link_id"],
    )

    if response.get("retCode") != 0:
        raise RuntimeError(
            f"Bybit history error: {response.get('retMsg')}"
        )

    matches = [
        row
        for row in response.get("result", {}).get("list", [])
        if row.get("orderLinkId") == intent["link_id"]
        and row.get("symbol") == intent["symbol"]
        and row.get("side") == intent["side"]
    ]

    if len(matches) != 1:
        return None

    order = matches[0]
    order_id = order.get("orderId")

    if not order_id or order.get("orderStatus") != "Filled":
        return None

    if intent.get("order_id") and intent["order_id"] != order_id:
        return None

    qty = Decimal(str(order.get("cumExecQty", "0")))
    price = Decimal(str(order.get("avgPrice") or "0"))

    if not (
        qty.is_finite() and qty > 0
        and price.is_finite() and price > 0
    ):
        return None

    saved = find_saved_order(order_id)

    if len(saved) != 1:
        return None

    trade = saved[0]

    if (
        trade["symbol"] != intent["symbol"]
        or trade["side"] != intent["side"]
        or Decimal(str(trade["qty"])) != qty
    ):
        return None

    return order_id


def recover_recorded_intents(session=None):
    """Only mark verified, already-saved orders as RECORDED."""
    intents = load_pending()

    if not intents:
        logger.info("Pending recovery: no unresolved intents")
        return {"checked": 0, "recovered": 0, "blocked": 0}

    if session is None:
        session = HTTP(
            testnet=TESTNET,
            demo=DEMO_MODE,
            api_key=API_KEY,
            api_secret=API_SECRET,
        )

    recovered = 0

    for intent in intents:
        try:
            order_id = verify_recorded_intent(session, intent)

            if order_id is None:
                logger.warning(
                    f"[{intent['symbol']}] Intent "
                    f"{intent['link_id']} remains BLOCKED"
                )
                continue

            mark_order(intent["link_id"], "RECORDED", order_id)
            recovered += 1

            logger.info(
                f"[{intent['symbol']}] Recovered saved order "
                f"{order_id}"
            )

        except Exception as exc:
            logger.error(
                f"[{intent['symbol']}] Recovery failed; "
                f"intent remains blocked: {exc}"
            )

    return {
        "checked": len(intents),
        "recovered": recovered,
        "blocked": len(intents) - recovered,
    }


def recover_missing_fills(session=None):
    """Recover verified Filled orders lacking a Neon trade.

    No Bybit place/close/cancel calls.
    Unknown, partial, conflicting or rejected orders remain blocked.
    """
    from datetime import datetime, timezone

    intents = load_pending()
    if not intents:
        return {"checked": 0, "recovered": 0}

    if session is None:
        session = HTTP(
            testnet=TESTNET,
            demo=DEMO_MODE,
            api_key=API_KEY,
            api_secret=API_SECRET,
        )

    recovered = 0

    for intent in intents:
        symbol = intent["symbol"]
        link_id = intent["link_id"]

        try:
            response = session.get_order_history(
                category="linear",
                symbol=symbol,
                orderLinkId=link_id,
            )

            if response.get("retCode") != 0:
                raise RuntimeError("Bybit order history unavailable")

            matches = [
                order
                for order in response.get(
                    "result", {}
                ).get("list", [])
                if order.get("orderLinkId") == link_id
                and order.get("symbol") == symbol
                and order.get("side") == intent["side"]
            ]

            if len(matches) != 1:
                continue

            order = matches[0]

            if order.get("orderStatus") != "Filled":
                continue

            order_id = order.get("orderId")
            if not order_id:
                continue

            if (
                intent.get("order_id")
                and intent["order_id"] != order_id
            ):
                continue

            qty = Decimal(str(order.get("cumExecQty", "0")))
            price = Decimal(str(order.get("avgPrice") or "0"))

            if not (
                qty.is_finite() and qty > 0
                and price.is_finite() and price > 0
            ):
                continue

            opened_ms = int(order.get("createdTime") or 0)
            if opened_ms <= 0:
                continue

            opened_at = datetime.fromtimestamp(
                opened_ms / 1000, tz=timezone.utc
            ).replace(tzinfo=None)

            def optional_level(value):
                try:
                    result = Decimal(str(value or "0"))
                    return result if result.is_finite() and result > 0 else None
                except (TypeError, ValueError, ArithmeticError):
                    return None

            sl = optional_level(order.get("stopLoss"))
            tp = optional_level(order.get("takeProfit"))

            with get_conn() as conn:
                with conn.cursor() as cur:
                    # Serialize reconciliation against other DB writers.
                    cur.execute(
                        "LOCK TABLE trades IN SHARE ROW EXCLUSIVE MODE"
                    )

                    cur.execute(
                        """
                        SELECT id, symbol, side, qty
                        FROM trades
                        WHERE order_id = %s
                        """,
                        (order_id,),
                    )
                    saved = cur.fetchall()

                    if len(saved) > 1:
                        raise RuntimeError(
                            "Duplicate saved order IDs"
                        )

                    if saved:
                        row = saved[0]
                        if (
                            row["symbol"] != symbol
                            or row["side"] != intent["side"]
                            or Decimal(str(row["qty"])) != qty
                        ):
                            raise RuntimeError(
                                "Existing trade does not match Bybit fill"
                            )
                    else:
                        cur.execute(
                            """
                            SELECT id FROM trades
                            WHERE symbol = %s AND status = 'OPEN'
                            LIMIT 1
                            """,
                            (symbol,),
                        )
                        if cur.fetchone():
                            raise RuntimeError(
                                "Other OPEN trade exists for symbol"
                            )

                        cur.execute(
                            """
                            INSERT INTO trades
                                (time, symbol, side, entry_price, qty,
                                 stop_loss, take_profit, status, order_id)
                            VALUES
                                (%s, %s, %s, %s, %s, %s, %s,
                                 'OPEN', %s)
                            RETURNING id
                            """,
                            (
                                opened_at, symbol, intent["side"],
                                price, qty, sl, tp, order_id,
                            ),
                        )

                        if not cur.fetchone():
                            raise RuntimeError(
                                "Recovery insert failed"
                            )

                    # Intent and trade are committed atomically.
                    cur.execute(
                        """
                        UPDATE trade_order_intents
                        SET status = 'RECORDED',
                            order_id = %s,
                            updated_at = NOW()
                        WHERE link_id = %s
                          AND status IN (
                              'PENDING', 'ACKNOWLEDGED',
                              'UNCERTAIN', 'FILLED_UNSAVED'
                          )
                        RETURNING link_id
                        """,
                        (order_id, link_id),
                    )
                    if not cur.fetchone():
                        raise RuntimeError(
                            "Recovery intent changed concurrently"
                        )

                conn.commit()

            recovered += 1
            logger.info(
                f"[{symbol}] Verified order recovered: {order_id}"
            )

        except Exception as exc:
            logger.error(
                f"[{symbol}] Missing fill recovery blocked: {exc}"
            )

    return {"checked": len(intents), "recovered": recovered}
