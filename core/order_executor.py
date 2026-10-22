import uuid
from decimal import Decimal, ROUND_DOWN
from typing import Any, cast

from pybit.unified_trading import HTTP
from config.settings import API_KEY, API_SECRET, DEMO_MODE, TESTNET, SYMBOL
from utils.logger import logger


class OrderExecutor:
    def __init__(self, symbol: str = SYMBOL):
        self.session = HTTP(
            testnet=TESTNET,
            demo=DEMO_MODE,
            api_key=API_KEY,
            api_secret=API_SECRET,
        )
        self.symbol = symbol
        self._tick_size = None
        self._qty_step = None
        self._min_qty = None
        self._load_instrument_info()

    @property
    def ready(self) -> bool:
        """False if the symbol's precision could not be loaded (bad symbol)."""
        return self._tick_size is not None and self._qty_step is not None

    # ------------------------------------------------------------------
    # Instrument info (tick size, qty step)
    # ------------------------------------------------------------------
    def _load_instrument_info(self):
        try:
            resp = cast(
                dict[str, Any],
                self.session.get_instruments_info(category="linear", symbol=self.symbol),
            )
            if resp["retCode"] != 0 or not resp["result"]["list"]:
                logger.error(f"[{self.symbol}] Instrument info error: {resp.get('retMsg')}")
                return
            info = resp["result"]["list"][0]
            self._tick_size = Decimal(info["priceFilter"]["tickSize"])
            self._qty_step = Decimal(info["lotSizeFilter"]["qtyStep"])
            self._min_qty = Decimal(info["lotSizeFilter"]["minOrderQty"])
            logger.info(
                f"[{self.symbol}] tick={self._tick_size} "
                f"qtyStep={self._qty_step} minQty={self._min_qty}"
            )
        except Exception as e:
            logger.error(f"[{self.symbol}] _load_instrument_info exception: {e}")

    def _round_price(self, price: float):
        if self._tick_size is None:
            return None
        p = (Decimal(str(price)) / self._tick_size).to_integral_value(
            rounding=ROUND_DOWN
        ) * self._tick_size
        return format(p, "f")

    def _round_qty(self, qty: float):
        if self._qty_step is None:
            return None
        q = (Decimal(str(qty)) / self._qty_step).to_integral_value(
            rounding=ROUND_DOWN
        ) * self._qty_step
        if self._min_qty is not None and q < self._min_qty:
            logger.error(
                f"[{self.symbol}] Qty {q} is below min order qty {self._min_qty}. "
                f"Increase TRADE_USDT."
            )
            return None
        return format(q, "f")

    # ------------------------------------------------------------------
    # Positions (real state from Bybit)
    # ------------------------------------------------------------------
    def get_open_position(self):
        """Open position dict for this symbol, or None if flat."""
        try:
            resp = cast(
                dict[str, Any],
                self.session.get_positions(category="linear", symbol=self.symbol),
            )
            if resp["retCode"] != 0:
                logger.error(f"[{self.symbol}] get_positions error: {resp['retMsg']}")
                return None
            for pos in resp["result"]["list"]:
                if float(pos.get("size", 0)) > 0:
                    return pos
            return None
        except Exception as e:
            logger.error(f"[{self.symbol}] get_open_position exception: {e}")
            return None

    def has_open_position(self) -> bool:
        return self.get_open_position() is not None

    def count_open_positions(self):
        """Number of open USDT-perp positions across ALL symbols.
        Returns None if the request failed (caller should skip trading)."""
        try:
            resp = cast(
                dict[str, Any],
                self.session.get_positions(
                    category="linear", settleCoin="USDT", limit=200
                ),
            )
            if resp["retCode"] != 0:
                logger.error(f"count_open_positions error: {resp['retMsg']}")
                return None
            return sum(1 for p in resp["result"]["list"] if float(p.get("size", 0)) > 0)
        except Exception as e:
            logger.error(f"count_open_positions exception: {e}")
            return None

    def set_leverage(self, leverage: int):
        try:
            resp = cast(
                dict[str, Any],
                self.session.set_leverage(
                    category="linear",
                    symbol=self.symbol,
                    buyLeverage=str(leverage),
                    sellLeverage=str(leverage),
                ),
            )
            if resp["retCode"] not in (0, 110043):  # 110043 = already set
                logger.error(f"[{self.symbol}] set_leverage error: {resp['retMsg']}")
            else:
                logger.info(f"[{self.symbol}] Leverage set to {leverage}x")
        except Exception as e:
            if "110043" in str(e):
                return
            logger.error(f"[{self.symbol}] set_leverage exception: {e}")

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    def place_market_order(self, levels: dict):
        """levels from RiskManager.calculate_levels(). side = "Buy" or "Sell"."""
        if not self.ready:
            logger.error(f"[{self.symbol}] Executor not ready (instrument info missing)")
            return None

        qty = self._round_qty(levels["quantity"])
        sl = self._round_price(levels["stop_loss"])
        tp = self._round_price(levels["take_profit"])
        if qty is None or sl is None or tp is None:
            return None

        try:
            resp = cast(
                dict[str, Any],
                self.session.place_order(
                    category="linear",
                    symbol=self.symbol,
                    side=levels["side"],
                    orderType="Market",
                    qty=qty,
                    stopLoss=sl,
                    takeProfit=tp,
                    slTriggerBy="LastPrice",
                    tpTriggerBy="LastPrice",
                    tpslMode="Full",
                    positionIdx=0,  # one-way mode
                    orderLinkId=f"bot-{uuid.uuid4().hex[:16]}",
                ),
            )
            if resp["retCode"] != 0:
                logger.error(f"[{self.symbol}] Order rejected: {resp['retCode']} {resp['retMsg']}")
                return None

            result = resp["result"]
            logger.info(
                f"[{self.symbol}] {levels['side']} {qty} | SL={sl} TP={tp} | "
                f"orderId={result.get('orderId')}"
            )
            return result
        except Exception as e:
            logger.error(f"[{self.symbol}] place_market_order exception: {e}")
            return None

    def close_position(self):
        """Close this symbol's position at market (reduce-only)."""
        pos = self.get_open_position()
        if pos is None:
            logger.info(f"[{self.symbol}] No open position to close")
            return None

        close_side = "Sell" if pos["side"] == "Buy" else "Buy"
        try:
            resp = cast(
                dict[str, Any],
                self.session.place_order(
                    category="linear",
                    symbol=self.symbol,
                    side=close_side,
                    orderType="Market",
                    qty=pos["size"],
                    reduceOnly=True,
                    positionIdx=0,
                ),
            )
            if resp["retCode"] != 0:
                logger.error(f"[{self.symbol}] Close rejected: {resp['retCode']} {resp['retMsg']}")
                return None
            logger.info(f"[{self.symbol}] Closed {pos['side']} position size={pos['size']}")
            return resp["result"]
        except Exception as e:
            logger.error(f"[{self.symbol}] close_position exception: {e}")
            return None