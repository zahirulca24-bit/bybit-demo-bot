from core.market_data import MarketData
from core.strategy import Strategy

md = MarketData()
df = md.get_candles(limit=100)

st = Strategy()
df_with_indicators = st.calculate_indicators(df)
signal = st.get_signal(df)

print("\n--- Last 5 Candles with Indicators ---")
print(df_with_indicators[["timestamp","close","ema_fast","ema_slow","rsi"]].tail(5).to_string())
print(f"\nCurrent Signal: {signal}")
