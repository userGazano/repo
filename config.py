import os
from dotenv import load_dotenv

load_dotenv()

# ========== BOT ==========
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', '@Withoutx4')

# ========== TELEGRAM API ==========
TELEGRAM_API_ID = int(os.getenv('TELEGRAM_API_ID'))
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')

# ========== DATABASE ==========
DATABASE_URL = os.getenv('DATABASE_URL')

# ========== SHOP ==========
SHOP_NAME = os.getenv('SHOP_NAME', 'PHYSICAL SHOP')
CURRENCY = os.getenv('CURRENCY', '₽')
