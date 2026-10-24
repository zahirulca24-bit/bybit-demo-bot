
import unittest
from unittest.mock import MagicMock, patch
import main


class PreflightTests(unittest.TestCase):

    def setUp(self):
        self.old_lock = main.trading_lock
        main.trading_lock = MagicMock()
        self.conn = MagicMock()
        self.conn.__enter__.return_value = self.conn
        self.cursor = (
            self.conn.cursor.return_value
            .__enter__.return_value
        )

    def tearDown(self):
        main.trading_lock = self.old_lock

    def test_open_trade_blocks_submission(self):
        self.cursor.fetchone.return_value = {"id": 2}
        with patch.object(main, "get_conn", return_value=self.conn), \
             patch.object(main, "assert_bot_lock"), \
             patch.object(main, "pending_symbols") as pending:
            with self.assertRaises(RuntimeError):
                main.preflight_trade("SOLUSDT")
            pending.assert_not_called()

    def test_pending_intent_blocks_submission(self):
        self.cursor.fetchone.return_value = None
        with patch.object(main, "get_conn", return_value=self.conn), \
             patch.object(main, "assert_bot_lock"), \
             patch.object(
                 main, "pending_symbols",
                 return_value={"BNBUSDT"},
             ):
            with self.assertRaises(RuntimeError):
                main.preflight_trade("BNBUSDT")

    def test_lock_failure_blocks_submission(self):
        with patch.object(
            main, "assert_bot_lock",
            side_effect=RuntimeError("Lock lost"),
        ), patch.object(main, "get_conn") as get_conn:
            with self.assertRaises(RuntimeError):
                main.preflight_trade("BTCUSDT")
            get_conn.assert_not_called()

    def test_healthy_preflight(self):
        self.cursor.fetchone.return_value = None
        with patch.object(main, "get_conn", return_value=self.conn), \
             patch.object(main, "assert_bot_lock"), \
             patch.object(
                 main, "pending_symbols",
                 return_value=set(),
             ):
            self.assertTrue(main.preflight_trade("BTCUSDT"))


if __name__ == "__main__":
    unittest.main()
