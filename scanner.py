
import time as _t
import pandas as pd
import numpy as np
from pybit.unified_trading import HTTP
from config.settings import (
    API_KEY, API_SECRET, DEMO_MODE, TESTNET, TIMEFRAME
)
from core.strategy import Strategy
from utils.logger import logger


class MarketScanner:
    TOP_N = 30

    def __init__(self):
        self.session = HTTP(
            testnet=TESTNET,
            demo=DEMO_MODE,
            api_key=API_KEY,
            api_secret=API_SECRET,
        )
        self.strategy = Strategy()

    def _top_syms(self):
        try:
            r = self.session.get_tickers(category="linear")
            if r.get("retCode") != 0:
                raise RuntimeError(r.get("retMsg", "Ticker API failed"))

            rows = [
                t for t in r.get("result", {}).get("list", [])
                if t.get("symbol", "").endswith("USDT")
                and float(t.get("turnover24h", 0)) > 0
            ]
            # Quote-currency turnover is comparable across symbols.
            rows.sort(
                key=lambda t: float(t.get("turnover24h", 0)),
                reverse=True
            )
            return [t["symbol"] for t in rows[:self.TOP_N]]
        except Exception as e:
            logger.error(f"[Scan] Top symbols failed: {e}")
            return []

    def _candles(self, sym):
        try:
            r = self.session.get_kline(
                category="linear",
                symbol=sym,
                interval=TIMEFRAME,
                limit=150,
            )
            if r.get("retCode") != 0:
                raise RuntimeError(r.get("retMsg", "Kline API failed"))

            rows = r.get("result", {}).get("list", [])
            if not rows:
                return None

            df = pd.DataFrame(
                rows,
                columns=[
                    "timestamp", "open", "high", "low",
                    "close", "volume", "turnover"
                ],
            )

            for col in (
                "timestamp", "open", "high", "low",
                "close", "volume", "turnover"
            ):
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df = df.dropna().sort_values("timestamp")
            df = df.drop_duplicates("timestamp")

            if df.empty:
                return None

            if (df["close"] <= 0).any():
                return None

            # Only completed candles: exclude the active bar.
            interval_ms = int(TIMEFRAME) * 60 * 1000
            now_ms = int(_t.time() * 1000)
            current_bar_start = (now_ms // interval_ms) * interval_ms

            df = df[df["timestamp"] < current_bar_start].copy()

            if len(df) < 40:
                logger.warning(
                    f"[Scan] {sym}: insufficient closed candles"
                )
                return None

            df["timestamp"] = pd.to_datetime(
                df["timestamp"], unit="ms", utc=True
            ).dt.tz_localize(None)

            return df.reset_index(drop=True)

        except Exception as e:
            logger.warning(f"[Scan] {sym}: candle error: {e}")
            return None

    def _math_predict(self, df):
        try:
            closes = df["close"].to_numpy(dtype=float)[-20:]
            if len(closes) < 20:
                return "N/A", 0.0
            if not np.isfinite(closes).all() or (closes <= 0).any():
                return "N/A", 0.0

            x = np.arange(len(closes))
            slope, intercept = np.polyfit(x, closes, 1)
            forecast = slope * len(closes) + intercept
            diff_pct = (forecast / closes[-1] - 1) * 100

            if not np.isfinite(diff_pct):
                return "N/A", 0.0
            if diff_pct > 0.05:
                return "BUY", float(diff_pct)
            if diff_pct < -0.05:
                return "SELL", float(diff_pct)
            return "HOLD", float(diff_pct)
        except Exception:
            return "N/A", 0.0

    def scan_one(self, sym):
        try:
            df = self._candles(sym)
            if df is None:
                return None

            tick = self.session.get_tickers(
                category="linear", symbol=sym
            )
            if tick.get("retCode") != 0:
                raise RuntimeError(tick.get("retMsg", "Ticker failed"))

            tickers = tick.get("result", {}).get("list", [])
            if len(tickers) != 1:
                raise RuntimeError("Ticker missing or ambiguous")

            td = tickers[0]
            if td.get("symbol") != sym:
                raise RuntimeError("Ticker symbol mismatch")

            price = float(td["lastPrice"])
            if not np.isfinite(price) or price <= 0:
                return None

            chg = float(td.get("price24hPcnt", 0)) * 100
            vol = float(td.get("volume24h", 0))

            di = self.strategy.calculate_indicators(df).dropna()
            if len(di) < 2:
                return None

            c = di.iloc[-1]
            sig = self.strategy.get_signal(df, sym)
            math_sig, math_pct = self._math_predict(df)

            rsi = float(c["rsi"])
            macd = float(c["macd"])
            ms = float(c["macd_signal"])
            ema_fast = float(c["ema_fast"])
            ema_slow = float(c["ema_slow"])

            if not np.isfinite(
                [rsi, macd, ms, ema_fast, ema_slow]
            ).all():
                return None

            score = 0
            reasons = []

            # Directional scoring; do not reward opposite momentum.
            if sig == "BUY":
                if rsi < 70:
                    score += 1
                    reasons.append("RSI permits BUY")
                if macd > ms:
                    score += 2
                    reasons.append("MACD bullish")
                if ema_fast > ema_slow:
                    score += 2
                    reasons.append("EMA bullish")
            elif sig == "SELL":
                if rsi > 30:
                    score += 1
                    reasons.append("RSI permits SELL")
                if macd < ms:
                    score += 2
                    reasons.append("MACD bearish")
                if ema_fast < ema_slow:
                    score += 2
                    reasons.append("EMA bearish")
            else:
                reasons.append("No EMA crossover confirmation")

            confirmed = (
                sig in ("BUY", "SELL")
                and math_sig == sig
            )
            if confirmed:
                score += 5
                reasons.append("Trend projection agrees")
            elif sig != "HOLD":
                reasons.append("Projection disagrees")

            return {
                "symbol": sym,
                "price": price,
                "change_pct": round(chg, 2),
                "volume_24h": round(vol, 0),
                "rsi": round(rsi, 2),
                "macd": round(macd, 4),
                "ema_fast": round(ema_fast, 4),
                "ema_slow": round(ema_slow, 4),
                "signal": sig,
                "math_signal": math_sig,
                "math_pct": round(math_pct, 3),
                "score": score,
                "reasons": ", ".join(reasons),
                "selected": confirmed and score >= 10,
            }

        except Exception as e:
            logger.error(f"[Scan] {sym}: {e}")
            return None

    def run(self, limit=20):
        t0 = _t.time()
        syms = self._top_syms()[:limit]
        logger.info(f"[Scan] Scanning {len(syms)} symbols")

        results = []
        for sym in syms:
            row = self.scan_one(sym)
            if row:
                results.append(row)
            _t.sleep(0.15)

        results.sort(
            key=lambda row: row["score"], reverse=True
        )
        selected = sum(bool(row["selected"]) for row in results)
        elapsed = round(_t.time() - t0, 1)

        logger.info(
            f"[Scan] {selected}/{len(results)} selected "
            f"in {elapsed}s"
        )

        return {
            "scanned_at": _t.strftime("%Y-%m-%d %H:%M:%S"),
            "total_scanned": len(results),
            "selected": selected,
            "duration_sec": elapsed,
            "results": results,
        }
