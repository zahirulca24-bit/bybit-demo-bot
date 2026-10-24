
import math

from config.settings import (
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
    TRADE_USDT,
    MAX_OPEN_TRADES,
)
from utils.logger import logger


class RiskManager:
    def __init__(self):
        self.stop_loss_pct = float(STOP_LOSS_PCT)
        self.take_profit_pct = float(TAKE_PROFIT_PCT)
        self.trade_usdt = float(TRADE_USDT)
        self.max_open_trades = int(MAX_OPEN_TRADES)

        if not (
            math.isfinite(self.stop_loss_pct)
            and 0 < self.stop_loss_pct < 1
        ):
            raise ValueError("STOP_LOSS_PCT must be between 0 and 1")

        if not (
            math.isfinite(self.take_profit_pct)
            and 0 < self.take_profit_pct < 1
        ):
            raise ValueError("TAKE_PROFIT_PCT must be between 0 and 1")

        if not (
            math.isfinite(self.trade_usdt)
            and self.trade_usdt > 0
        ):
            raise ValueError("TRADE_USDT must be positive")

        if self.max_open_trades < 1:
            raise ValueError("MAX_OPEN_TRADES must be at least 1")

    def can_trade(self, open_count=None):
        """Unknown position count must never permit a trade."""
        if (
            isinstance(open_count, bool)
            or not isinstance(open_count, int)
            or open_count < 0
        ):
            logger.error(
                "[RiskManager] Invalid open position count; blocked"
            )
            return False

        if open_count >= self.max_open_trades:
            logger.warning(
                f"Max open trades reached: "
                f"{open_count}/{self.max_open_trades}"
            )
            return False

        return True

    def calculate_levels(self, entry_price, side):
        """Calculate directional levels without premature price rounding."""
        try:
            entry = float(entry_price)
        except (ValueError, TypeError, OverflowError):
            raise ValueError("Invalid entry price")

        if not math.isfinite(entry) or entry <= 0:
            raise ValueError("Entry price must be positive and finite")

        if side not in ("Buy", "Sell"):
            raise ValueError("Side must be Buy or Sell")

        qty = self.trade_usdt / entry

        if not math.isfinite(qty) or qty <= 0:
            raise ValueError("Invalid calculated quantity")

        if side == "Buy":
            sl = entry * (1 - self.stop_loss_pct)
            tp = entry * (1 + self.take_profit_pct)
            directional_ok = 0 < sl < entry < tp
        else:
            sl = entry * (1 + self.stop_loss_pct)
            tp = entry * (1 - self.take_profit_pct)
            directional_ok = 0 < tp < entry < sl

        if not directional_ok:
            raise ValueError("Invalid SL/TP direction")

        if not all(
            math.isfinite(v) and v > 0
            for v in (sl, tp, qty)
        ):
            raise ValueError("Invalid risk levels")

        risk_usd = abs(entry - sl) * qty
        reward_usd = abs(tp - entry) * qty

        if not (
            math.isfinite(risk_usd)
            and math.isfinite(reward_usd)
            and risk_usd > 0
            and reward_usd > 0
        ):
            raise ValueError("Invalid risk/reward calculation")

        levels = {
            "entry": entry,
            "stop_loss": sl,
            "take_profit": tp,
            "quantity": qty,
            "side": side,
            "trade_usdt": self.trade_usdt,
            "risk_usd": round(risk_usd, 4),
            "reward_usd": round(reward_usd, 4),
        }

        logger.info(
            f"[RiskManager] {side} Entry={entry} "
            f"Qty={qty:.8f} SL={sl:.8f} TP={tp:.8f} "
            f"Risk={risk_usd:.4f} Reward={reward_usd:.4f}"
        )

        return levels
