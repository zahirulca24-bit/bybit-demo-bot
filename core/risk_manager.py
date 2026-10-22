from config.settings import STOP_LOSS_PCT, TAKE_PROFIT_PCT, TRADE_USDT, MAX_OPEN_TRADES
from utils.logger import logger


class RiskManager:
    def __init__(self):
        self.stop_loss_pct  = STOP_LOSS_PCT
        self.take_profit_pct = TAKE_PROFIT_PCT
        self.trade_usdt     = TRADE_USDT        # যেমন $100
        self.max_open_trades = MAX_OPEN_TRADES

    def can_trade(self, open_count: int = 0) -> bool:
        if open_count >= self.max_open_trades:
            logger.warning(f"Max open trades reached: {open_count}/{self.max_open_trades}")
            return False
        return True

    def calculate_levels(self, entry_price: float, side: str) -> dict:
        # Price থেকে Qty হিসাব — সব Symbol-এ সমান USDT
        quantity = self.trade_usdt / entry_price

        if side == "Buy":
            sl = round(entry_price * (1 - self.stop_loss_pct), 4)
            tp = round(entry_price * (1 + self.take_profit_pct), 4)
        else:
            sl = round(entry_price * (1 + self.stop_loss_pct), 4)
            tp = round(entry_price * (1 - self.take_profit_pct), 4)

        levels = {
            "entry":      entry_price,
            "stop_loss":  sl,
            "take_profit": tp,
            "quantity":   quantity,
            "side":       side,
            "trade_usdt": self.trade_usdt,
            "risk_usd":   round(abs(entry_price - sl) * quantity, 4),
            "reward_usd": round(abs(tp - entry_price) * quantity, 4),
        }

        logger.info(
            f"[RiskManager] {side} | Entry={entry_price} | "
            f"Qty={quantity:.6f} (~${self.trade_usdt}) | "
            f"SL={sl} | TP={tp} | "
            f"Risk=${levels['risk_usd']} | Reward=${levels['reward_usd']}"
        )
        return levels