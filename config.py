import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', '@Withoutx4')

TELEGRAM_API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')

# ✅ SQLite с абсолютным путём
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:////tmp/shop.db')

SHOP_NAME = os.getenv('SHOP_NAME', 'PHYSICAL SHOP')
CURRENCY = os.getenv('CURRENCY', '⭐️')

SESSIONS_DIR = '/tmp/sessions'
LOGS_DIR = '/tmp/logs'
