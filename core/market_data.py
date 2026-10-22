import pandas as pd
from typing import Any, cast
from pybit.unified_trading import HTTP
from config.settings import API_KEY, API_SECRET, DEMO_MODE, TESTNET, SYMBOL, TIMEFRAME
from utils.logger import logger

class MarketData:
    def __init__(self, symbol: str = SYMBOL):
        self.session = HTTP(
            testnet=TESTNET,
            demo=DEMO_MODE,
            api_key=API_KEY,
            api_secret=API_SECRET,
        )
        self.symbol = symbol
        self.timeframe = TIMEFRAME

    def get_candles(self, limit=100):
        try:
            response = self.session.get_kline(
                category="linear",
                symbol=self.symbol,
                interval=self.timeframe,
                limit=limit
            )
            if response["retCode"] != 0:
                logger.error(f"Candle fetch error: {response['retMsg']}")
                return None

            raw = response["result"]["list"]
            df = pd.DataFrame(raw, columns=[
                "timestamp", "open", "high", "low", "close", "volume", "turnover"
            ])
            df = df.astype({
                "timestamp": "int64",
                "open": "float64",
                "high": "float64",
                "low": "float64",
                "close": "float64",
                "volume": "float64",
            })
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df = df.sort_values("timestamp").reset_index(drop=True)
            return df
        except Exception as e:
            logger.error(f"get_candles exception: {e}")
            return None

    def get_current_price(self):
        try:
            ticker = self.session.get_tickers(category="linear", symbol=self.symbol)
            response = cast(Any, ticker)
            return float(response["result"]["list"][0]["lastPrice"])
        except Exception as e:
            logger.error(f"get_current_price exception: {e}")
            return None