
import math
import unittest
from core.risk_manager import RiskManager


class RiskSafetyTests(unittest.TestCase):
    def setUp(self):
        self.risk = RiskManager()

    def test_valid_buy_levels(self):
        x = self.risk.calculate_levels(100, "Buy")
        self.assertLess(x["stop_loss"], 100)
        self.assertGreater(x["take_profit"], 100)

    def test_valid_sell_levels(self):
        x = self.risk.calculate_levels(100, "Sell")
        self.assertGreater(x["stop_loss"], 100)
        self.assertLess(x["take_profit"], 100)

    def test_zero_price_rejected(self):
        with self.assertRaises(ValueError):
            self.risk.calculate_levels(0, "Buy")

    def test_nan_price_rejected(self):
        with self.assertRaises(ValueError):
            self.risk.calculate_levels(math.nan, "Buy")

    def test_invalid_side_rejected(self):
        with self.assertRaises(ValueError):
            self.risk.calculate_levels(100, "HOLD")

    def test_unknown_open_count_blocked(self):
        self.assertFalse(self.risk.can_trade(None))
        self.assertFalse(self.risk.can_trade(-1))
        self.assertFalse(
            self.risk.can_trade(self.risk.max_open_trades)
        )


if __name__ == "__main__":
    unittest.main()
