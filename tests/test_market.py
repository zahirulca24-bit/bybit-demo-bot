from core.market_data import MarketData

md = MarketData()
df = md.get_candles(limit=5)
if df is not None:
    print(df[["timestamp","open","high","low","close","volume"]])
price = md.get_current_price()
print(f"Current Price: {price}")
