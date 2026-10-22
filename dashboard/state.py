import time
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List

TRADE_LOG_FILE = "logs/trade_log.json"

def _load_trades() -> List[dict]:
    try:
        if os.path.exists(TRADE_LOG_FILE):
            with open(TRADE_LOG_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def _save_trades(trades: List[dict]):
    try:
        os.makedirs("logs", exist_ok=True)
        with open(TRADE_LOG_FILE, "w") as f:
            json.dump(trades, f, indent=2)
    except Exception:
        pass

@dataclass
class SymbolState:
    symbol: str = ""
    price: float = 0.0
    ema_fast: float = 0.0
    ema_slow: float = 0.0
    rsi: float = 0.0
    signal: str = "HOLD"
    has_position: bool = False
    position_side: str = ""
    position_size: float = 0.0
    unrealized_pnl: float = 0.0
    macd: float = 0.0
    macd_signal: float = 0.0
    macd_hist: float = 0.0
    updated_at: float = 0.0

@dataclass
class BotState:
    running: bool = False
    started_at: float = 0.0
    symbols: Dict[str, SymbolState] = field(default_factory=dict)
    trade_log: List[dict] = field(default_factory=_load_trades)

    def update_symbol(self, symbol, **kwargs):
        if symbol not in self.symbols:
            self.symbols[symbol] = SymbolState(symbol=symbol)
        s = self.symbols[symbol]
        for k, v in kwargs.items():
            if hasattr(s, k):
                setattr(s, k, v)
        s.updated_at = time.time()

    def add_trade(self, symbol, side, price, qty, sl, tp):
        self.trade_log.insert(0, {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol,
            "side": side,
            "price": price,
            "qty": qty,
            "sl": sl,
            "tp": tp,
        })
        if len(self.trade_log) > 100:
            self.trade_log.pop()
        _save_trades(self.trade_log)

bot_state = BotState()