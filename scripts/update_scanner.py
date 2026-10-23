import pathlib

code = '''import time as _t
import pandas as pd
import numpy as np
from pybit.unified_trading import HTTP
from config.settings import API_KEY, API_SECRET, DEMO_MODE, TESTNET, TIMEFRAME
from core.strategy import Strategy
from utils.logger import logger

class MarketScanner:
    TOP_N = 30
    def __init__(self):
        self.session = HTTP(testnet=TESTNET, demo=DEMO_MODE, api_key=API_KEY, api_secret=API_SECRET)
        self.strategy = Strategy()

    def _top_syms(self):
        try:
            r = self.session.get_tickers(category="linear")
            rows = [t for t in r["result"]["list"] if t["symbol"].endswith("USDT") and float(t.get("volume24h", 0)) > 0]
            rows.sort(key=lambda x: float(x["volume24h"]), reverse=True)
            return [t["symbol"] for t in rows[:self.TOP_N]]
        except Exception as e:
            logger.error(f"[Scan] top_syms:{e}")
            return []

    def _candles(self, sym):
        try:
            r = self.session.get_kline(category="linear", symbol=sym, interval=TIMEFRAME, limit=100)
            if r["retCode"] != 0: return None
            df = pd.DataFrame(r["result"]["list"], columns=["timestamp","open","high","low","close","volume","turnover"])
            df = df.astype({"timestamp": "int64", "open": "float64", "high": "float64", "low": "float64", "close": "float64", "volume": "float64"})
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            return df.sort_values("timestamp").reset_index(drop=True)
        except: return None

    def _math_predict(self, df):
        try:
            closes = df['close'].values[-20:]
            if len(closes) < 20: return "N/A", 0.0
            y = np.array(closes)
            x = np.arange(len(y))
            slope, intercept = np.polyfit(x, y, 1)
            predicted_price = (slope * len(y)) + intercept
            current_price = y[-1]
            diff_pct = ((predicted_price - current_price) / current_price) * 100
            if diff_pct > 0.05: return "BUY", diff_pct
            elif diff_pct < -0.05: return "SELL", diff_pct
            else: return "HOLD", diff_pct
        except: return "N/A", 0.0

    def scan_one(self, sym):
        try:
            df = self._candles(sym)
            if df is None: return None
            td = self.session.get_tickers(category="linear", symbol=sym)["result"]["list"][0]
            price = float(td["lastPrice"])
            chg = round(float(td.get("price24hPcnt", 0)) * 100, 2)
            vol = float(td.get("volume24h", 0))

            di = self.strategy.calculate_indicators(df).dropna()
            if di.empty: return None
            c = di.iloc[-1]
            sig = self.strategy.get_signal(df, sym)

            # ম্যাথমেটিক্যাল প্রেডিকশন
            math_sig, math_pct = self._math_predict(df)

            score, reasons = 0, []
            rsi = float(c["rsi"])
            macd = float(c.get("macd", 0))
            ms = float(c.get("macd_signal", 0))

            if rsi <= 30: score += 3; reasons.append(f"RSI Oversold {rsi:.1f}")
            elif rsi >= 70: score += 3; reasons.append(f"RSI Overbought {rsi:.1f}")
            elif rsi <= 40: score += 1; reasons.append(f"RSI Low {rsi:.1f}")
            elif rsi >= 60: score += 1; reasons.append(f"RSI High {rsi:.1f}")

            if macd > ms: score += 2; reasons.append("MACD Bullish")
            else: score += 1; reasons.append("MACD Bearish")

            if c["ema_fast"] > c["ema_slow"]: score += 1; reasons.append("EMA Bull Align")
            else: reasons.append("EMA Bear Align")

            # টেকনিক্যাল ও ম্যাথ সিগন্যাল মিললে বোনাস স্কোর
            if sig != "HOLD" and math_sig == sig:
                score += 5
                reasons.append(f"Math Confirms {sig}")
            elif sig != "HOLD":
                score += 5
                reasons.append(f"Signal:{sig}")

            return {"symbol": sym, "price": price, "change_pct": chg, "volume_24h": round(vol, 0),
                    "rsi": round(rsi, 2), "macd": round(macd, 4),
                    "ema_fast": round(float(c["ema_fast"]), 4), "ema_slow": round(float(c["ema_slow"]), 4),
                    "signal": sig, "math_signal": math_sig, "math_pct": round(math_pct, 3),
                    "score": score, "reasons": ", ".join(reasons),
                    "selected": score >= 5 or (sig != "HOLD" and math_sig == sig)}
        except Exception as e:
            logger.error(f"[Scan] {sym}:{e}")
            return None

    def run(self, limit=20):
        t0 = _t.time()
        syms = self._top_syms()[:limit]
        logger.info(f"[Scan] Scanning {len(syms)} symbols...")
        results = []
        for sym in syms:
            r = self.scan_one(sym)
            if r: results.append(r)
            _t.sleep(0.15)
        results.sort(key=lambda x: x["score"], reverse=True)
        sel = [r for r in results if r["selected"]]
        dur = round(_t.time() - t0, 1)
        logger.info(f"[Scan] Done {dur}s | {len(sel)}/{len(results)} selected")
        return {"scanned_at": _t.strftime("%Y-%m-%d %H:%M:%S"), "total_scanned": len(results),
                "selected": len(sel), "duration_sec": dur, "results": results}
'''
pathlib.Path('scanner.py').write_text(code.strip(), encoding='utf-8')
print('\\n[SUCCESS] scanner.py updated with Math Prediction!\\n')
