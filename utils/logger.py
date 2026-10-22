import logging
import os
from datetime import datetime

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"logs/bot_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("bybit-bot")
