import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import main


class TradeSyncTests(unittest.TestCase):

    def setUp(self):
        main.open_trades.clear()
        main.blocked_symbols.clear()

    def tearDown(self):
        main.open_trades.clear()
        main.blocked_symbols.clear()

    def fake_connection(self, rows=None):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = rows or []
        cursor.fetchone.return_value = {"id": 2}
        return conn, cursor

    def test_restart_recovers_open_trades(self):
        rows = [{
            "id": 2,
            "time": datetime(2026, 10, 22, 12, 0),
            "symbol": "SOLUSDT",
            "side": "Sell",
            "entry_price": 104.18,
            "qty": 0.9,
        }]

        conn, cursor = self.fake_connection(rows)

        with patch.object(main, "get_conn", return_value=conn):
            result = main.recover_open_trades()

        self.assertIn("SOLUSDT", result)
        self.assertEqual(result["SOLUSDT"]["db_id"], 2)
        self.assertEqual(result["SOLUSDT"]["qty"], 0.9)
        self.assertEqual(result["SOLUSDT"]["side"], "Sell")
        cursor.execute.assert_called_once()

    def test_duplicate_open_records_block_symbol(self):
        rows = [
            {
                "id": 2, "time": datetime(2026, 10, 22),
                "symbol": "ETHUSDT", "side": "Buy",
                "entry_price": 2394.26, "qty": 0.04,
            },
            {
                "id": 3, "time": datetime(2026, 10, 21),
                "symbol": "ETHUSDT", "side": "Buy",
                "entry_price": 2390, "qty": 0.04,
            },
        ]

        conn, _ = self.fake_connection(rows)

        with patch.object(main, "get_conn", return_value=conn):
            result = main.recover_open_trades()

        self.assertIn("ETHUSDT", main.blocked_symbols)
        self.assertEqual(len(result), 1)

    def test_confirmed_fill_uses_actual_quantity(self):
        executor = MagicMock()
        executor.symbol = "BNBUSDT"
        executor.session.get_order_history.return_value = {
            "retCode": 0,
            "result": {
                "list": [{
                    "orderId": "order-123",
                    "symbol": "BNBUSDT",
                    "side": "Buy",
                    "orderStatus": "Filled",
                    "cumExecQty": "0.13",
                    "avgPrice": "731.32",
                }]
            },
        }

        result = main.confirmed_fill(
            executor, "order-123", "Buy"
        )

        self.assertEqual(result, (0.13, 731.32))

    def test_unconfirmed_fill_returns_none(self):
        executor = MagicMock()
        executor.symbol = "ETHUSDT"
        executor.session.get_order_history.return_value = {
            "retCode": 0,
            "result": {
                "list": [{
                    "orderId": "order-456",
                    "symbol": "ETHUSDT",
                    "side": "Buy",
                    "orderStatus": "New",
                    "cumExecQty": "0",
                    "avgPrice": "0",
                }]
            },
        }

        with patch.object(main.time, "sleep"):
            result = main.confirmed_fill(
                executor, "order-456", "Buy"
            )

        self.assertIsNone(result)
        self.assertEqual(
            executor.session.get_order_history.call_count, 8
        )

    def test_api_failure_never_confirms_fill(self):
        executor = MagicMock()
        executor.symbol = "SOLUSDT"
        executor.session.get_order_history.return_value = {
            "retCode": 10006,
            "retMsg": "Rate limit",
            "result": {"list": []},
        }

        with patch.object(main.time, "sleep"):
            result = main.confirmed_fill(
                executor, "order-789", "Sell"
            )

        self.assertIsNone(result)

    def test_flat_without_matching_pnl_does_not_close_db(self):
        opened = datetime(2026, 10, 22, 12, 0)

        main.open_trades["SOLUSDT"] = {
            "db_id": 2,
            "side": "Sell",
            "entry_price": 104.18,
            "qty": 0.9,
            "opened_at": opened,
        }

        executor = MagicMock()
        executor.session.get_closed_pnl.return_value = {
            "retCode": 0,
            "result": {"list": []},
        }

        with patch.object(main, "get_conn") as get_conn:
            main.check_closed("SOLUSDT", executor, None)

        get_conn.assert_not_called()
        self.assertIn("SOLUSDT", main.open_trades)
        self.assertIn("SOLUSDT", main.blocked_symbols)

    def test_verified_close_updates_db(self):
        opened = datetime(2026, 10, 22, 12, 0)
        closed = opened + timedelta(hours=1)

        main.open_trades["SOLUSDT"] = {
            "db_id": 2,
            "side": "Sell",
            "entry_price": 104.18,
            "qty": 0.9,
            "opened_at": opened,
        }

        executor = MagicMock()
        executor.session.get_closed_pnl.return_value = {
            "retCode": 0,
            "result": {
                "list": [{
                    "createdTime": str(
                        int(closed.timestamp() * 1000)
                    ),
                    "closedSize": "0.9",
                    "avgEntryPrice": "104.18",
                    "avgExitPrice": "103.5",
                    "closedPnl": "0.5",
                    "side": "Sell",
                }]
            },
        }

        conn, cursor = self.fake_connection()

        with patch.object(main, "get_conn", return_value=conn), \
             patch.object(main, "alert_trade_closed") as alert:
            main.check_closed("SOLUSDT", executor, None)

        cursor.execute.assert_called_once()
        conn.commit.assert_called_once()
        alert.assert_called_once()
        self.assertNotIn("SOLUSDT", main.open_trades)


if __name__ == "__main__":
    unittest.main()
