import unittest
from decimal import Decimal
from scripts.reconcile import validate_fill


class ReconcileTests(unittest.TestCase):

    def setUp(self):
        self.trade = {
            "order_id": "abc123",
            "symbol": "ETHUSDT",
            "side": "Buy",
        }
        self.order = {
            "orderId": "abc123",
            "symbol": "ETHUSDT",
            "side": "Buy",
            "orderStatus": "Filled",
            "cumExecQty": "0.04",
        }

    def test_valid_fill(self):
        result = validate_fill(self.trade, [self.order])
        self.assertEqual(result, Decimal("0.04"))

    def test_wrong_order(self):
        with self.assertRaises(ValueError):
            validate_fill(self.trade, [])

    def test_wrong_symbol(self):
        order = dict(self.order, symbol="BTCUSDT")
        with self.assertRaises(ValueError):
            validate_fill(self.trade, [order])

    def test_unfilled_order(self):
        order = dict(self.order, orderStatus="New")
        with self.assertRaises(ValueError):
            validate_fill(self.trade, [order])

    def test_zero_quantity(self):
        order = dict(self.order, cumExecQty="0")
        with self.assertRaises(ValueError):
            validate_fill(self.trade, [order])


if __name__ == "__main__":
    unittest.main()
