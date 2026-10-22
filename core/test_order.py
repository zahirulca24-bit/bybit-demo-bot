from core.order_executor import OrderExecutor
from core.risk_manager import RiskManager
from core.market_data import MarketData

ex = OrderExecutor()
price = MarketData().get_current_price()
levels = RiskManager().calculate_levels(price, "Buy")

print("ORDER:", ex.place_market_order(levels))
print("POSITION:", ex.get_open_position())