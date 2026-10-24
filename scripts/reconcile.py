"""Read-only preview or guarded Neon quantity reconciliation."""

import argparse
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def validate_fill(trade, orders):
    matches = [
        o for o in orders
        if o.get("orderId") == trade["order_id"]
    ]

    if len(matches) != 1:
        raise ValueError("Opening order not uniquely matched")

    order = matches[0]

    if order.get("symbol") != trade["symbol"]:
        raise ValueError("Symbol mismatch")
    if order.get("side") != trade["side"]:
        raise ValueError("Side mismatch")
    if order.get("orderStatus") != "Filled":
        raise ValueError("Order not fully filled")

    qty = Decimal(str(order.get("cumExecQty", "0")))
    if not qty.is_finite() or qty <= 0:
        raise ValueError("Invalid executed quantity")

    return qty


def reconcile(apply=False):
    from database import get_conn
    from pybit.unified_trading import HTTP
    from config.settings import (
        API_KEY, API_SECRET, DEMO_MODE, TESTNET
    )

    session = HTTP(
        testnet=TESTNET,
        demo=DEMO_MODE,
        api_key=API_KEY,
        api_secret=API_SECRET,
    )

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, symbol, side, qty, order_id
                FROM trades
                WHERE status = 'OPEN'
                ORDER BY id
            """)
            trades = [dict(r) for r in cur.fetchall()]

    print(f"OPEN RECORDS: {len(trades)}")
    changes = []
    skipped = 0

    for trade in trades:
        try:
            if not trade["order_id"]:
                raise ValueError("Missing opening order ID")

            response = session.get_order_history(
                category="linear",
                symbol=trade["symbol"],
                orderId=trade["order_id"],
            )

            if response.get("retCode") != 0:
                raise RuntimeError(response.get("retMsg"))

            orders = response.get("result", {}).get("list", [])
            filled_qty = validate_fill(trade, orders)
            neon_qty = Decimal(str(trade["qty"]))

            print(
                f"ID={trade['id']} {trade['symbol']} "
                f"Neon={neon_qty} Filled={filled_qty}"
            )

            if filled_qty != neon_qty:
                changes.append((trade, filled_qty))
                print("  ACTION: UPDATE QTY")
            else:
                print("  ACTION: NO CHANGE")

        except Exception as exc:
            skipped += 1
            print(f"  SKIPPED ID={trade['id']}: {exc}")

    print(
        f"SUMMARY: {len(changes)} changes, "
        f"{skipped} skipped"
    )

    if not apply:
        print("DRY RUN: Database unchanged")
        return

    if skipped:
        print("APPLY BLOCKED: Some records unverified")
        raise SystemExit(1)

    if not changes:
        print("NOTHING TO UPDATE")
        return

    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                for trade, filled_qty in changes:
                    cur.execute("""
                        UPDATE trades
                        SET qty = %s
                        WHERE id = %s
                          AND symbol = %s
                          AND side = %s
                          AND order_id = %s
                          AND status = 'OPEN'
                          AND qty = %s
                        RETURNING id
                    """, (
                        filled_qty,
                        trade["id"],
                        trade["symbol"],
                        trade["side"],
                        trade["order_id"],
                        trade["qty"],
                    ))

                    if cur.fetchone() is None:
                        raise RuntimeError(
                            f"Concurrent change: ID={trade['id']}"
                        )

            conn.commit()
            print(f"APPLIED: {len(changes)} quantity updates")

        except Exception:
            conn.rollback()
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    reconcile(apply=args.apply)
