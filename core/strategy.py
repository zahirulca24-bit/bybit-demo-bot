import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, ema_indicator
from config.settings import (
    EMA_FAST, EMA_SLOW, RSI_PERIOD,
    RSI_OVERBOUGHT, RSI_OVERSOLD
)
from utils.logger import logger


class Strategy:
    def __init__(self):
        self.ema_fast = EMA_FAST
        self.ema_slow = EMA_SLOW
        self.rsi_period = RSI_PERIOD
        self.rsi_ob = RSI_OVERBOUGHT
        self.rsi_os = RSI_OVERSOLD

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # EMA
        df["ema_fast"] = ema_indicator(df["close"], window=self.ema_fast)
        df["ema_slow"] = ema_indicator(df["close"], window=self.ema_slow)

        # RSI
        df["rsi"] = RSIIndicator(df["close"], window=self.rsi_period).rsi()

        # MACD
        macd = MACD(df["close"], window_slow=26, window_fast=12, window_sign=9)
        df["macd"]        = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_hist"]   = macd.macd_diff()

        return df

    def get_signal(self, df: pd.DataFrame, symbol: str = "") -> str:
        # Reject malformed prices before technical indicators run.
        if df is None or len(df) < 40 or "close" not in df:
            return "HOLD"

        prices = pd.to_numeric(df["close"], errors="coerce")
        if prices.isna().any() or (prices <= 0).any():
            return "HOLD"

        if "timestamp" in df.columns:
            times = pd.to_datetime(df["timestamp"], errors="coerce")
            if times.isna().any() or not times.is_monotonic_increasing:
                return "HOLD"

        df = self.calculate_indicators(df)
        df = df.dropna().reset_index(drop=True)

        if len(df) < 2:
            return "HOLD"

        prev = df.iloc[-2]
        curr = df.iloc[-1]

        # --- EMA Cross ---
        ema_cross_up   = prev["ema_fast"] < prev["ema_slow"] and curr["ema_fast"] > curr["ema_slow"]
        ema_cross_down = prev["ema_fast"] > prev["ema_slow"] and curr["ema_fast"] < curr["ema_slow"]

        # --- RSI Filter ---
        rsi_ok_buy  = curr["rsi"] < self.rsi_ob   # not overbought
        rsi_ok_sell = curr["rsi"] > self.rsi_os   # not oversold

        # --- MACD Confirmation ---
        macd_bullish = curr["macd"] > curr["macd_signal"]
        macd_bearish = curr["macd"] < curr["macd_signal"]

        # --- Final Signal ---
        if ema_cross_up and rsi_ok_buy and macd_bullish:
            signal = "BUY"
        elif ema_cross_down and rsi_ok_sell and macd_bearish:
            signal = "SELL"
        else:
            signal = "HOLD"

        logger.info(
            f"[{symbol}] "
            f"EMA_F={curr['ema_fast']:.4f} EMA_S={curr['ema_slow']:.4f} | "
            f"RSI={curr['rsi']:.2f} | "
            f"MACD={curr['macd']:.4f} SIG={curr['macd_signal']:.4f} | "
            f"=> {signal}"
        )
        return signal