
import unittest
from unittest.mock import MagicMock, patch

from core import pending_order_recovery as recovery


class PendingRecoveryTests(unittest.TestCase):

    def setUp(self):
        self.intent = {
            "link_id": "bot-abc",
            "symbol": "BNBUSDT",
            "side": "Buy",
            "status": "FILLED_UNSAVED",
            "order_id": "order-123",
        }

        self.session = MagicMock()
        self.session.get_order_history.return_value = {
            "retCode": 0,
            "result": {
                "list": [{
                    "orderLinkId": "bot-abc",
                    "orderId": "order-123",
                    "symbol": "BNBUSDT",
                    "side": "Buy",
                    "orderStatus": "Filled",
                    "cumExecQty": "0.13",
                    "avgPrice": "731.32",
                }]
            },
        }

    @patch.object(recovery, "find_saved_order")
    def test_saved_fill_is_verified(self, find_saved):
        find_saved.return_value = [{
            "id": 3,
            "symbol": "BNBUSDT",
            "side": "Buy",
            "qty": "0.13",
            "order_id": "order-123",
        }]

        result = recovery.verify_recorded_intent(
            self.session, self.intent
        )
        self.assertEqual(result, "order-123")

    @patch.object(recovery, "find_saved_order")
    def test_missing_trade_remains_blocked(self, find_saved):
        find_saved.return_value = []
        result = recovery.verify_recorded_intent(
            self.session, self.intent
        )
        self.assertIsNone(result)

    @patch.object(recovery, "find_saved_order")
    def test_wrong_qty_remains_blocked(self, find_saved):
        find_saved.return_value = [{
            "id": 3,
            "symbol": "BNBUSDT",
            "side": "Buy",
            "qty": "0.13673905",
            "order_id": "order-123",
        }]

        result = recovery.verify_recorded_intent(
            self.session, self.intent
        )
        self.assertIsNone(result)

    def test_bybit_api_failure_raises(self):
        self.session.get_order_history.return_value = {
            "retCode": 10006,
            "retMsg": "Rate limit",
        }

        with self.assertRaises(RuntimeError):
            recovery.verify_recorded_intent(
                self.session, self.intent
            )

    @patch.object(recovery, "mark_order")
    @patch.object(recovery, "verify_recorded_intent")
    @patch.object(recovery, "load_pending")
    def test_success_marks_recorded(
        self, load_pending, verify, mark
    ):
        load_pending.return_value = [self.intent]
        verify.return_value = "order-123"

        result = recovery.recover_recorded_intents(
            self.session
        )

        self.assertEqual(result["recovered"], 1)
        mark.assert_called_once_with(
            "bot-abc", "RECORDED", "order-123"
        )

    @patch.object(recovery, "mark_order")
    @patch.object(recovery, "verify_recorded_intent")
    @patch.object(recovery, "load_pending")
    def test_uncertain_order_is_not_released(
        self, load_pending, verify, mark
    ):
        load_pending.return_value = [self.intent]
        verify.return_value = None

        result = recovery.recover_recorded_intents(
            self.session
        )

        self.assertEqual(result["blocked"], 1)
        mark.assert_not_called()


if __name__ == "__main__":
    unittest.main()
