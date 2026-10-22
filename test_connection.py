from pybit.unified_trading import HTTP
from config.settings import API_KEY, API_SECRET, DEMO_MODE, TESTNET, SYMBOL
from utils.logger import logger

def test_connection():
    logger.info("Bybit Demo API connection test starting...")

    session = HTTP(
        testnet=TESTNET,
        demo=DEMO_MODE,
        api_key=API_KEY,
        api_secret=API_SECRET,
    )

    try:
        # Account Balance চেক
        balance = session.get_wallet_balance(accountType="UNIFIED")
        if balance["retCode"] == 0:
            coins = balance["result"]["list"][0]["coin"]
            for coin in coins:
                if coin["coin"] == "USDT":
                    logger.info(f"USDT Balance: {coin['walletBalance']}")
            logger.info("Connection SUCCESS!")
        else:
            logger.error(f"Error: {balance['retMsg']}")

        # BTC Price চেক
        ticker = session.get_tickers(category="linear", symbol=SYMBOL)
        price = ticker["result"]["list"][0]["lastPrice"]
        logger.info(f"{SYMBOL} Current Price: {price}")

    except Exception as e:
        logger.error(f"Connection FAILED: {e}")

if __name__ == "__main__":
    test_connection()
