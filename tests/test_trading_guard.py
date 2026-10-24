import unittest
from unittest.mock import MagicMock, patch

from core import trading_guard as guard


class TradingGuardTests(unittest.TestCase):

    def setUp(self):
        self.conn = MagicMock()
        self.conn.__enter__.return_value = self.conn

        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = (
            self.cursor
        )

        self.db_patch = patch.object(
            guard, "get_conn", return_value=self.conn
        )
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()

    def test_lock_acquired(self):
        self.cursor.fetchone.return_value = {
            "acquired": True
        }

        result = guard.acquire_bot_lock()

        self.assertIs(result, self.conn)
        self.conn.close.assert_not_called()

    def test_second_instance_blocked(self):
        self.cursor.fetchone.return_value = {
            "acquired": False
        }

        result = guard.acquire_bot_lock()

        self.assertIsNone(result)
        self.conn.close.assert_called_once()

    def test_lock_error_fails_closed(self):
        self.cursor.execute.side_effect = (
            RuntimeError("DB connection failed")
        )

        with self.assertRaises(RuntimeError):
            guard.acquire_bot_lock()

        self.conn.close.assert_called_once()

    def test_order_intent_reserved(self):
        self.cursor.fetchone.return_value = {
            "link_id": "bot-test"
        }

        result = guard.reserve_order(
            "BTCUSDT", "Buy"
        )

        self.assertTrue(result.startswith("bot-"))
        self.cursor.execute.assert_called_once()
        self.conn.close.assert_called_once()

    def test_duplicate_intent_blocked(self):
        self.cursor.fetchone.return_value = None

        with self.assertRaises(RuntimeError):
            guard.reserve_order("BTCUSDT", "Buy")

        self.conn.close.assert_called_once()

    def test_pending_symbols_recovered(self):
        self.cursor.fetchall.return_value = [
            {"symbol": "SOLUSDT"},
            {"symbol": "BNBUSDT"},
        ]

        result = guard.pending_symbols()

        self.assertEqual(
            result, {"SOLUSDT", "BNBUSDT"}
        )

    def test_mark_order_missing_fails(self):
        self.cursor.fetchone.return_value = None

        with self.assertRaises(RuntimeError):
            guard.mark_order(
                "bot-test",
                "ACKNOWLEDGED",
                "order-123",
            )

        self.conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
