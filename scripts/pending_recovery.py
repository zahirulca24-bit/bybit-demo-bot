"""Read-only Bybit/Neon pending-order recovery inspection."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from decimal import Decimal
from pybit.unified_trading import HTTP
from config.settings import API_KEY, API_SECRET, DEMO_MODE, TESTNET
from database import get_conn


ACTIVE = (
    "PENDING",
    "ACKNOWLEDGED",
    "UNCERTAIN",
    "FILLED_UNSAVED",
)


def load_intents():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT link_id, symbol, side, status, order_id
                FROM trade_order_intents
                WHERE status = ANY(%s)
                ORDER BY created_at
            """, (list(ACTIVE),))
            return [dict(row) for row in cur.fetchall()]


def find_saved_trade(order_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, symbol, side, qty, status
                FROM trades
                WHERE order_id = %s
            """, (order_id,))
            return [dict(row) for row in cur.fetchall()]


def inspect_intent(session, intent):
    symbol = intent["symbol"]
    link_id = intent["link_id"]

    print(
        f"\n{symbol} | {link_id} | "
        f"Neon intent={intent['status']}"
    )

    try:
        response = session.get_order_history(
            category="linear",
            symbol=symbol,
            orderLinkId=link_id,
        )

        if response.get("retCode") != 0:
            print("BLOCKED: Bybit API error")
            return

        orders = [
            item
            for item in response.get("result", {}).get("list", [])
            if item.get("orderLinkId") == link_id
            and item.get("symbol") == symbol
        ]

        if len(orders) != 1:
            print(
                "BLOCKED: Order missing or ambiguous. "
                "Not proof that it was never placed."
            )
            return

        order = orders[0]
        order_id = order.get("orderId")

        if order.get("side") != intent["side"]:
            print("BLOCKED: Order side mismatch")
            return

        status = order.get("orderStatus")
        qty = Decimal(str(order.get("cumExecQty", "0")))
        price = Decimal(str(order.get("avgPrice") or "0"))

        print(
            f"Bybit status={status} "
            f"filled_qty={qty} avg_price={price}"
        )

        if not order_id:
            print("BLOCKED: Missing Bybit order ID")
            return

        saved = find_saved_trade(order_id)

        if len(saved) > 1:
            print("BLOCKED: Multiple database trade matches")
            return

        if len(saved) == 1:
            record = saved[0]

            if (
                record["symbol"] != symbol
                or record["side"] != intent["side"]
                or Decimal(str(record["qty"])) != qty
            ):
                print("BLOCKED: Saved trade details mismatch")
                return

            if status == "Filled" and qty > 0 and price > 0:
                print(
                    f"RECOVERABLE: Trade ID={record['id']} "
                    "already exists in Neon"
                )
            else:
                print("REVIEW: Trade exists but fill is unconfirmed")
            return

        if status == "Filled" and qty > 0 and price > 0:
            print(
                "FILLED_UNSAVED: Bybit fill confirmed, "
                "but no matching Neon trade exists"
            )
        else:
            print(
                "BLOCKED: No verified saved trade; "
                "do not submit a replacement order"
            )

    except Exception as exc:
        print(
            f"BLOCKED: Inspection error "
            f"({type(exc).__name__})"
        )


def main():
    intents = load_intents()
    print(f"UNRESOLVED INTENTS: {len(intents)}")

    if not intents:
        print("No pending-order recovery required")
        return

    session = HTTP(
        testnet=TESTNET,
        demo=DEMO_MODE,
        api_key=API_KEY,
        api_secret=API_SECRET,
    )

    for intent in intents:
        inspect_intent(session, intent)

    print("\nREAD ONLY: No database or Bybit changes made")


if __name__ == "__main__":
    main()
