import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BYBIT_API_KEY", "")
API_SECRET = os.getenv("BYBIT_API_SECRET", "")

DEMO_MODE = True
TESTNET = False

_raw = os.getenv("SYMBOLS", "BTCUSDT")
SYMBOLS = [s.strip() for s in _raw.split(",")]
SYMBOL = SYMBOLS[0]

TIMEFRAME = os.getenv("TIMEFRAME", "15")
TRADE_USDT = float(os.getenv("TRADE_USDT", "100"))
TRADE_QUANTITY = float(os.getenv("TRADE_QUANTITY", "0.001"))

EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

STOP_LOSS_PCT = 0.015
TAKE_PROFIT_PCT = 0.03
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", "1"))