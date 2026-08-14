import os
import logging
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from config import (
    BOT_TOKEN, ADMIN_ID, ADMIN_USERNAME, SHOP_NAME, CURRENCY,
    TELEGRAM_API_ID, TELEGRAM_API_HASH, SESSIONS_DIR, LOGS_DIR
)
from database import get_session, User, Category, Account, UserAccount, Transaction
from telethon_manager import TelethonManager
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes,
    CallbackQueryHandler, ConversationHandler
)

Path(LOGS_DIR).mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{LOGS_DIR}/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

telethon_mgr = TelethonManager(TELEGRAM_API_ID, TELEGRAM_API_HASH, SESSIONS_DIR)

# ==================== КОНСТАНТЫ ====================

(AUTH_PHONE, AUTH_CODE, AUTH_2FA, SELECT_CATEGORY, ADMIN_AUTH_PHONE, 
 ADMIN_AUTH_CODE, ADMIN_AUTH_2FA, ADMIN_SELECT_CATEGORY) = range(8)

# ==================== HELPERS ====================

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def get_main_keyboard():
    """Reply-клавиатура главного меню"""
    keyboard = [
        [KeyboardButton("🛍️ Магазин"), KeyboardButton("💰 Профиль")],
        [KeyboardButton("📱 Мои аккаунты"), KeyboardButton("💬 Поддержка")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_profile_keyboard():
    """Reply-клавиатура профиля"""
    keyboard = [
        [KeyboardButton("📱 Мои аккаунты"), KeyboardButton("⭐️ Пополнить баланс")],
        [KeyboardButton("🛍️ В магазин"), KeyboardButton("◀️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_account_keyboard():
    """Reply-клавиатура управления аккаунтом"""
    keyboard = [
        [KeyboardButton("🔄 Получить новый код"), KeyboardButton("◀️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def extract_code(text: str) -> Optional[str]:
    """Извлечение 5-значного кода из текста"""
    patterns = [
        r'(?:код|code)[\s:]*(\d{5})',
        r'(\d{5})\s+is\s+your',
        r'telegram[\s:]*(\d{5})',
        r'^(\d{5})$',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None

# ==================== USER HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Стартовое сообщение"""
    user_id = update.effective_user.id
    db = get_session()
    
    user = db.query(User).filter_by(telegram_id=user_id).first()
    if not user:
        user = User(
            telegram_id=user_id,
            username=update.effective_user.username,
            balance=0.0
        )
        db.add(user)
        db.commit()
    
    db.close()
    
    text = f"""
╔════════════════════════════════════╗
║  🎁 {SHOP_NAME} 🎁
║  Продажа аккаунтов Telegram
╚════════════════════════════════════╝

👋 Добро пожаловать, {update.effective_user.first_name}!

💰 Баланс: {user.balance}⭐️
📱 Ваш ID: {user.telegram_id}

Выберите действие:
"""
    
    await update.message.reply_text(text, reply_markup=get_main_keyboard())
    context.user_data.clear()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    text = update.message.text
    user_id = update.effective_user.id
    db = get_session()
    user = db.query(User).filter_by(telegram_id=user_id).first()
    
    if text == "🛍️ Магазин":
        await shop_menu(update, context, db)
    
    elif text == "💰 Профиль":
        await profile_menu(update, context, db)
    
    elif text == "📱 Мои аккаунты":
        await my_accounts(update, context, db)
    
    elif text == "💬 Поддержка":
        await update.message.reply_text(
            f"💬 Связь с поддержкой:\n\n@{ADMIN_USERNAME.replace('@', '')}",
            reply_markup=get_main_keyboard()
        )
    
    elif text == "◀️ Назад":
        await start(update, context)
    
    elif text == "⭐️ Пополнить баланс":
        await top_up_menu(update, context)
    
    elif text == "🔄 Получить новый код":
        if 'current_account_id' in context.user_data:
            await send_code_for_account(update, context, context.user_data['current_account_id'])
        else:
            await update.message.reply_text("❌ Ошибка. Вернись в профиль.")
    
    else:
        await update.message.reply_text("❓ Неизвестная команда", reply_markup=get_main_keyboard())
    
    db.close()

async def shop_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, db):
    """Меню магазина"""
    categories = db.query(Category).all()
    
    if not categories:
        await update.message.reply_text(
            "📭 Нет категорий",
            reply_markup=get_main_keyboard()
        )
        return
    
    text = f"""
╔════════════════════════════════════╗
║  🛍️ МАГАЗИН 🛍️
╚════════════════════════════════════╝

"""
    keyboard = []
    
    for cat in categories:
        available = db.query(Account).filter_by(
            category_id=cat.id, available=True
        ).count()
        
        text += f"🔹 {cat.emoji} <b>{cat.name}</b>\n"
        text += f"   💰 {cat.price}⭐️  |  📦 Доступно: {available}\n\n"
        
        keyboard.append([InlineKeyboardButton(
            f"{cat.emoji} {cat.name} ({available})",
            callback_data=f'cat_{cat.id}'
        )])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='back_to_main')])
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def category_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр категории"""
    query = update.callback_query
    await query.answer()
    
    category_id = int(query.data.split('_')[1])
    db = get_session()
    
    cat = db.query(Category).filter_by(id=category_id).first()
    accounts = db.query(Account).filter_by(category_id=category_id, available=True).all()
    
    if not accounts:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='shop')]]
        await query.edit_message_text(
            "❌ Нет доступных аккаунтов",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        db.close()
        return
    
    text = f"""
╔════════════════════════════════════╗
║  {cat.emoji} {cat.name.upper()} {cat.emoji}
╚════════════════════════════════════╝

📊 <b>Информация:</b>
💰 Цена: <code>{cat.price}⭐️</code>
📦 Доступно: <code>{len(accounts)}</code>

💬 После покупки ты получишь аккаунт с кодом входа.
"""
    
    keyboard = [
        [InlineKeyboardButton(f"💳 Купить за {cat.price}⭐️", callback_data=f'buy_cat_{category_id}')],
        [InlineKeyboardButton("◀️ Назад", callback_data='shop')]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    db.close()

async def buy_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Покупка аккаунта"""
    query = update.callback_query
    await query.answer()
    
    category_id = int(query.data.split('_')[2])
    user_id = query.from_user.id
    
    db = get_session()
    user = db.query(User).filter_by(telegram_id=user_id).first()
    cat = db.query(Category).filter_by(id=category_id).first()
    accounts = db.query(Account).filter_by(category_id=category_id, available=True).all()
    
    if not accounts:
        await query.edit_message_text("❌ Аккаунты закончились")
        db.close()
        return
    
    if user.balance < cat.price:
        await query.edit_message_text(
            f"❌ <b>Недостаточно звёзд</b>\n\n"
            f"💰 Ваш баланс: <code>{user.balance}⭐️</code>\n"
            f"💳 Нужно: <code>{cat.price}⭐️</code>\n"
            f"📉 Не хватает: <code>{cat.price - user.balance}⭐️</code>",
            parse_mode='HTML'
        )
        db.close()
        return
    
    account = random.choice(accounts)
    
    # Уменьшаем баланс и отмечаем как проданный
    user.balance -= cat.price
    account.available = False
    account.sold_to = user_id
    
    user_account = UserAccount(user_id=user_id, account_id=account.id)
    transaction = Transaction(user_id=user_id, type='purchase', amount=cat.price)
    
    db.add(user_account)
    db.add(transaction)
    db.commit()
    
    text = f"""
╔════════════════════════════════════╗
║  ✅ ПОКУПКА УСПЕШНА! ✅
╚════════════════════════════════════╝

{cat.emoji} <b>{cat.name}</b>
📱 <code>{account.phone}</code>

⏭️ <b>Что дальше?</b>
1️⃣ Нажми кнопку "Получить код"
2️⃣ Введи код в Telegram
3️⃣ Готово! Аккаунт в твоём распоряжении

💰 Баланс: <code>{user.balance}⭐️</code>
"""
    
    keyboard = [
        [InlineKeyboardButton("📨 Получить код", callback_data=f'get_code_{account.id}')],
        [InlineKeyboardButton("🛍️ Ещё покупки", callback_data='shop')]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    db.close()

async def profile_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, db):
    """Профиль пользователя"""
    user = db.query(User).filter_by(telegram_id=update.effective_user.id).first()
    accounts_count = db.query(UserAccount).filter_by(user_id=update.effective_user.id).count()
    
    text = f"""
╔════════════════════════════════════╗
║  👤 ПРОФИЛЬ 👤
╚════════════════════════════════════╝

👥 <b>Информация:</b>
🆔 ID: <code>{user.telegram_id}</code>
💬 Ник: @{user.username or 'unknown'}
📅 Дата: {user.created_at.strftime('%d.%m.%Y')}

💰 <b>Баланс:</b> <code>{user.balance}⭐️</code>
📱 <b>Аккаунтов:</b> <code>{accounts_count}</code>

✅ Статус: Активен
"""
    
    await update.message.reply_text(text, reply_markup=get_profile_keyboard(), parse_mode='HTML')

async def top_up_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню пополнения баланса"""
    keyboard = [
        [InlineKeyboardButton("100⭐️", callback_data='topup_100')],
        [InlineKeyboardButton("500⭐️", callback_data='topup_500')],
        [InlineKeyboardButton("1000⭐️", callback_data='topup_1000')],
        [InlineKeyboardButton("◀️ Назад", callback_data='back_profile')]
    ]
    
    text = f"""
╔════════════════════════════════════╗
║  ⭐️ ПОПОЛНИТЬ БАЛАНС ⭐️
╚════════════════════════════════════╝

Выберите количество звёзд:
"""
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def my_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE, db):
    """Мои купленные аккаунты"""
    user_accounts = db.query(UserAccount).filter_by(
        user_id=update.effective_user.id
    ).all()
    
    if not user_accounts:
        await update.message.reply_text(
            "📭 У тебя нет аккаунтов\n\n🛍️ Купи в магазине!",
            reply_markup=get_profile_keyboard()
        )
        return
    
    text = f"""
╔════════════════════════════════════╗
║  📱 МОИ АККАУНТЫ 📱
║  Всего: {len(user_accounts)}
╚════════════════════════════════════╝

"""
    keyboard = []
    
    for ua in user_accounts:
        account = db.query(Account).filter_by(id=ua.account_id).first()
        cat = db.query(Category).filter_by(id=account.category_id).first()
        text += f"🔹 {cat.emoji} <b>{cat.name}</b>\n   📱 <code>{account.phone}</code>\n\n"
        keyboard.append([InlineKeyboardButton(
            f"📨 {account.phone}",
            callback_data=f'get_code_{account.id}'
        )])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='back_profile')])
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def get_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить код входа для аккаунта"""
    query = update.callback_query
    await query.answer()
    
    account_id = int(query.data.split('_')[2])
    db = get_session()
    account = db.query(Account).filter_by(id=account_id).first()
    cat = db.query(Category).filter_by(id=account.category_id).first()
    
    if not account:
        await query.edit_message_text("❌ Аккаунт не найден")
        db.close()
        return
    
    # Проверяем, авторизован ли уже аккаунт
    code = telethon_mgr.get_code(account_id)
    
    if code:
        text = f"""
╔════════════════════════════════════╗
║  ✅ КОД ВХОДА ✅
╚════════════════════════════════════╝

{cat.emoji} <b>{cat.name}</b>
📱 {account.phone}

🔐 <b>КОД:</b>
<code>{code}</code>

⏱️ Действителен 10 минут
💡 Введи его в Telegram для входа
"""
    else:
        text = f"""
╔════════════════════════════════════╗
║  ⏳ ПОЛУЧЕНИЕ КОДА ⏳
╚════════════════════════════════════╝

{cat.emoji} <b>{cat.name}</b>
📱 {account.phone}

🔄 Код отправляется на номер...
📲 Проверь входящие сообщения Telegram

Если код не пришёл через 30 сек:
→ Попробуй обновить
"""
    
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data=f'get_code_{account_id}')],
        [InlineKeyboardButton("◀️ Назад", callback_data='back_accounts')]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    db.close()

async def send_code_for_account(update: Update, context: ContextTypes.DEFAULT_TYPE, account_id: int):
    """Отправить код для аккаунта"""
    db = get_session()
    account = db.query(Account).filter_by(id=account_id).first()
    cat = db.query(Category).filter_by(id=account.category_id).first()
    
    code = telethon_mgr.get_code(account_id)
    
    if code:
        text = f"""
╔════════════════════════════════════╗
║  ✅ КОД ВХОДА ✅
╚════════════════════════════════════╝

{cat.emoji} <b>{cat.name}</b>
📱 {account.phone}

🔐 <b>КОД:</b>
<code>{code}</code>

⏱️ Действителен 10 минут
"""
    else:
        text = f"""
╔════════════════════════════════════╗
║  ⏳ ОЖИДАНИЕ КОДА ⏳
╚════════════════════════════════════╝

📱 {account.phone}

🔄 Отправляем запрос...
📲 Проверь входящие в Telegram
"""
    
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=get_account_keyboard())
    db.close()

# ==================== ADMIN HANDLERS ====================

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-панель"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Доступ запрещён")
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить аккаунт", callback_data='admin_add_start')],
        [InlineKeyboardButton("📋 Все аккаунты", callback_data='admin_list_all')],
        [InlineKeyboardButton("📂 Категории", callback_data='admin_categories')],
        [InlineKeyboardButton("⭐️ Выдать баланс", callback_data='admin_give_balance')],
        [InlineKeyboardButton("📱 Выдать аккаунт", callback_data='admin_give_account')]
    ]
    
    text = """
╔════════════════════════════════════╗
║  ⚙️ АДМИН-ПАНЕЛЬ ⚙️
╚════════════════════════════════════╝

Управление магазином
"""
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def admin_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало добавления аккаунта (вход как в enivvv)"""
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📱 <b>Введи номер телефона</b>\n\nПример: +79991234567",
        parse_mode='HTML'
    )
    context.user_data['mode'] = 'admin_request_phone'
    return ADMIN_AUTH_PHONE

async def admin_handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка админ команд"""
    if not is_admin(update.effective_user.id):
        return
    
    mode = context.user_data.get('mode')
    text = update.message.text.strip()
    
    if mode == 'admin_request_phone':
        phone = text
        if not phone.startswith('+'):
            phone = '+' + phone
        
        if len(phone) < 10:
            await update.message.reply_text("❌ Неверный формат")
            return ADMIN_AUTH_PHONE
        
        context.user_data['admin_phone'] = phone
        context.user_data['admin_account_id'] = hash(phone) % 1000000
        
        await update.message.reply_text(f"⏳ Отправляю код на {phone}...")
        success, message = await telethon_mgr.request_code(
            context.user_data['admin_account_id'],
            phone
        )
        
        if success:
            await update.message.reply_text(f"✅ {message}\n\n📝 Введи 5-значный код")
            context.user_data['mode'] = 'admin_verify_code'
        else:
            await update.message.reply_text(f"❌ {message}")
            context.user_data['mode'] = None
        
        return ADMIN_AUTH_CODE
    
    elif mode == 'admin_verify_code':
        code = text.strip()
        
        if not code.isdigit() or len(code) != 5:
            await update.message.reply_text("❌ Код должен быть 5 цифр")
            return ADMIN_AUTH_CODE
        
        phone = context.user_data['admin_phone']
        
        await update.message.reply_text("⏳ Проверяю...")
        success, message = await telethon_mgr.verify_code(phone, code)
        
        if success:
            await update.message.reply_text(f"✅ {message}\n\n📂 Выбери категорию (ID)")
            context.user_data['mode'] = 'admin_select_category'
        elif message == "2FA_REQUIRED":
            await update.message.reply_text("🔐 Введи пароль 2FA")
            context.user_data['mode'] = 'admin_verify_2fa'
        else:
            await update.message.reply_text(f"❌ {message}")
            context.user_data['mode'] = None
        
        return ADMIN_AUTH_2FA
    
    elif mode == 'admin_verify_2fa':
        password = text.strip()
        phone = context.user_data['admin_phone']
        
        await update.message.reply_text("⏳ Проверяю...")
        success, message = await telethon_mgr.verify_2fa(phone, password)
        
        if success:
            await update.message.reply_text(f"✅ {message}\n\n📂 Выбери категорию (ID)")
            context.user_data['mode'] = 'admin_select_category'
        else:
            await update.message.reply_text(f"❌ {message}")
            context.user_data['mode'] = None
        
        return ADMIN_AUTH_2FA
    
    elif mode == 'admin_select_category':
        try:
            category_id = int(text)
            db = get_session()
            cat = db.query(Category).filter_by(id=category_id).first()
            
            if not cat:
                await update.message.reply_text("❌ Категория не найдена")
                db.close()
                return ADMIN_SELECT_CATEGORY
            
            phone = context.user_data['admin_phone']
            account_id = context.user_data['admin_account_id']
            
            account = Account(category_id=category_id, phone=phone)
            db.add(account)
            db.commit()
            db.close()
            
            await update.message.reply_text(
                f"✅ <b>Аккаунт добавлен!</b>\n\n"
                f"{cat.emoji} {cat.name}\n"
                f"📱 {phone}\n"
                f"📡 Слушаю входящие коды...",
                parse_mode='HTML'
            )
            context.user_data.clear()
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")
            context.user_data['mode'] = None
        
        return ADMIN_SELECT_CATEGORY
    
    elif mode == 'give_balance':
        try:
            parts = text.split()
            user_id = int(parts[0])
            amount = float(parts[1])
            
            db = get_session()
            user = db.query(User).filter_by(telegram_id=user_id).first()
            if user:
                user.balance += amount
                db.commit()
                await update.message.reply_text(f"✅ +{amount}⭐️ пользователю {user_id}")
            else:
                await update.message.reply_text("❌ Пользователь не найден")
            db.close()
            context.user_data['mode'] = None
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")
    
    elif mode == 'give_account':
        try:
            parts = text.split()
            user_id = int(parts[0])
            category_id = int(parts[1])
            
            db = get_session()
            account = db.query(Account).filter_by(
                category_id=category_id, available=True
            ).first()
            
            if not account:
                await update.message.reply_text("❌ Нет доступных аккаунтов")
                db.close()
                return
            
            account.available = False
            account.sold_to = user_id
            user_account = UserAccount(user_id=user_id, account_id=account.id)
            db.add(user_account)
            db.commit()
            db.close()
            
            await update.message.reply_text(f"✅ Выдано {user_id}\n📱 {account.phone}")
            context.user_data['mode'] = None
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")

async def admin_list_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список всех аккаунтов"""
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    
    db = get_session()
    accounts = db.query(Account).all()
    
    text = "📋 <b>ВСЕ АККАУНТЫ:</b>\n\n"
    
    for acc in accounts:
        status = "✅ ПРОДАН" if not acc.available else "🟢 ДОСТУПЕН"
        cat = db.query(Category).filter_by(id=acc.category_id).first()
        text += f"{status} | {cat.emoji} {cat.name}\n📱 {acc.phone}\n\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='admin_back')]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    db.close()

async def admin_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление категориями"""
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    
    db = get_session()
    categories = db.query(Category).all()
    
    text = "📂 <b>КАТЕГОРИИ:</b>\n\n"
    keyboard = []
    
    for cat in categories:
        available = db.query(Account).filter_by(category_id=cat.id, available=True).count()
        text += f"{cat.emoji} {cat.name} - {cat.price}⭐️ ({available} акк)\n"
    
    keyboard.append([InlineKeyboardButton("➕ Новая категория", callback_data='admin_new_cat')])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='admin_back')])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    db.close()

async def admin_new_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создать категорию"""
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📝 Формат: <b>ЭМОДЗИ НАЗВАНИЕ ЦЕНА</b>\n\nПример: 🇺🇸 USA 100"
    )
    context.user_data['mode'] = 'new_category'

async def admin_give_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выдать баланс"""
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "⭐️ Формат: <b>USER_ID КОЛИЧЕСТВО</b>\n\nПример: 123456789 500"
    )
    context.user_data['mode'] = 'give_balance'

async def admin_give_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выдать аккаунт"""
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📱 Формат: <b>USER_ID CATEGORY_ID</b>\n\nПример: 123456789 1"
    )
    context.user_data['mode'] = 'give_account'

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Универсальный обработчик callback'ов"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'back_to_main':
        await start(update, context)
    elif query.data == 'back_profile':
        db = get_session()
        await profile_menu(update, context, db)
        db.close()
    elif query.data == 'back_accounts':
        db = get_session()
        await my_accounts(update, context, db)
        db.close()
    elif query.data == 'shop':
        db = get_session()
        await shop_menu(update, context, db)
        db.close()
    elif query.data == 'admin_back':
        await admin_start(update, context)
    elif query.data.startswith('cat_'):
        await category_view(update, context)
    elif query.data.startswith('buy_cat_'):
        await buy_account(update, context)
    elif query.data.startswith('get_code_'):
        await get_code(update, context)
    elif query.data.startswith('topup_'):
        amount = int(query.data.split('_')[1])
        await query.edit_message_text(
            f"⭐️ <b>Подтвердить покупку</b>\n\n"
            f"Вы покупаете: {amount}⭐️\n\n"
            f"<i>Нажмите кнопку ниже для оплаты звёздами</i>",
            parse_mode='HTML'
        )
    elif query.data == 'admin_add_start':
        await admin_add_start(update, context)
    elif query.data == 'admin_list_all':
        await admin_list_all(update, context)
    elif query.data == 'admin_categories':
        await admin_categories(update, context)
    elif query.data == 'admin_new_cat':
        await admin_new_cat(update, context)
    elif query.data == 'admin_give_balance':
        await admin_give_balance(update, context)
    elif query.data == 'admin_give_account':
        await admin_give_account(update, context)

# ==================== MAIN ====================

def main():
    logger.info("🚀 Бот запускается...")
    app = Application.builder().token(BOT_TOKEN).build()
    
    conv_add = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_start, pattern='admin_add_start')],
        states={
            ADMIN_AUTH_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handle_text)],
            ADMIN_AUTH_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handle_text)],
            ADMIN_AUTH_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handle_text)],
            ADMIN_SELECT_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handle_text)],
        },
        fallbacks=[CommandHandler('cancel', lambda u, c: ConversationHandler.END)],
    )
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('/admin', admin_start))
    
    app.add_handler(conv_add)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    logger.info("✅ Бот готов")
    app.run_polling()

if __name__ == '__main__':
    main()
