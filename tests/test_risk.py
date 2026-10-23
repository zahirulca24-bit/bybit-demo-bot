from core.risk_manager import RiskManager
from core.market_data import MarketData

md = MarketData()
price = md.get_current_price()

rm = RiskManager()

print("--- BUY Trade Levels ---")
buy_levels = rm.calculate_levels(price, "Buy")
for k, v in buy_levels.items():
    print(f"  {k}: {v}")

print("\n--- SELL Trade Levels ---")
sell_levels = rm.calculate_levels(price, "Sell")
for k, v in sell_levels.items():
    print(f"  {k}: {v}")

print(f"\nCan Trade: {rm.can_trade()}")
