import os
import logging
from pathlib import Path
from datetime import datetime
from config import BOT_TOKEN, ADMIN_ID, ADMIN_USERNAME, SHOP_NAME, CURRENCY, TELEGRAM_API_ID, TELEGRAM_API_HASH
from database import get_session, User, Account, Transaction
from telethon_manager import TelethonManager

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes,
    CallbackQueryHandler
)

Path('logs').mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

telethon_mgr = TelethonManager(TELEGRAM_API_ID, TELEGRAM_API_HASH)

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

# ==================== USER HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = get_session()
    
    user = db.query(User).filter_by(telegram_id=user_id).first()
    if not user:
        user = User(telegram_id=user_id, username=update.effective_user.username)
        db.add(user)
        db.commit()
    
    db.close()
    
    keyboard = [
        [InlineKeyboardButton("🛍️ Магазин", callback_data='shop')],
        [InlineKeyboardButton("💰 Профиль", callback_data='profile')],
        [InlineKeyboardButton(f"💬 Поддержка ({ADMIN_USERNAME})", url=f'https://t.me/{ADMIN_USERNAME.replace("@", "")}')]
    ]
    
    await update.message.reply_text(
        f"👋 Добро пожаловать в <b>{SHOP_NAME}</b>\n\n🎁 Продажа физических аккаунтов",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    db = get_session()
    accounts = db.query(Account).filter_by(sold=False).all()
    db.close()
    
    if not accounts:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back')]]
        await query.edit_message_text("📭 Нет аккаунтов", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    text = f"🛍️ <b>Магазин</b>\n\n"
    keyboard = []
    
    for acc in accounts:
        text += f"📱 {acc.name} — {acc.price}{CURRENCY}\n"
        keyboard.append([InlineKeyboardButton(f"Купить: {acc.name}", callback_data=f'buy_{acc.id}')])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='back')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    account_id = int(query.data.split('_')[1])
    db = get_session()
    
    account = db.query(Account).filter_by(id=account_id, sold=False).first()
    if not account:
        await query.edit_message_text("❌ Недоступно")
        db.close()
        return
    
    user = db.query(User).filter_by(telegram_id=query.from_user.id).first()
    
    if user.balance < account.price:
        await query.edit_message_text(f"❌ Мало денег\nБаланс: {user.balance}{CURRENCY}")
        db.close()
        return
    
    user.balance -= account.price
    account.sold = True
    account.sold_to = query.from_user.id
    account.sold_at = datetime.now()
    
    transaction = Transaction(
        user_id=query.from_user.id,
        account_id=account_id,
        amount=account.price,
        status='completed'
    )
    
    db.add(transaction)
    db.commit()
    db.close()
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back')]]
    await query.edit_message_text(
        f"✅ <b>Куплено!</b>\n📱 {account.name}\n📱 {account.phone}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    db = get_session()
    user = db.query(User).filter_by(telegram_id=query.from_user.id).first()
    accounts = db.query(Account).filter_by(sold_to=query.from_user.id).all()
    db.close()
    
    text = (
        f"👤 <b>Профиль @{user.username or 'unknown'}</b>\n\n"
        f"🆔 ID: {user.telegram_id}\n"
        f"💰 Баланс: {user.balance}{CURRENCY}\n"
        f"📅 Дата регистрации: {user.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        f"✅ Активен\n"
        f"👤 Пользователь"
    )
    
    keyboard = []
    if accounts:
        keyboard.append([InlineKeyboardButton("📱 Мои аккаунты", callback_data='my_accounts')])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='back')])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def my_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    db = get_session()
    accounts = db.query(Account).filter_by(sold_to=query.from_user.id).all()
    db.close()
    
    if not accounts:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='profile')]]
        await query.edit_message_text("📭 Нет аккаунтов", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    text = f"📱 <b>Мои аккаунты</b>\n\n"
    keyboard = []
    
    for acc in accounts:
        text += f"📱 {acc.name}\n📱 {acc.phone}\n\n"
        keyboard.append([InlineKeyboardButton(f"📨 Получить код: {acc.name}", callback_data=f'get_code_{acc.id}')])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='profile')])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def get_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    account_id = int(query.data.split('_')[2])
    db = get_session()
    account = db.query(Account).filter_by(id=account_id).first()
    db.close()
    
    if not account:
        await query.edit_message_text("❌ Аккаунт не найден")
        return
    
    code = telethon_mgr.get_code(account_id)
    
    if code:
        text = f"✅ <b>КОД:</b>\n\n<code>{code}</code>\n\n⏱️ Действителен 10 минут"
    else:
        text = f"⏳ <b>Ожидание кода...</b>\n\n📱 Номер: {account.phone}\n\nПроверь входящие СМС"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data=f'get_code_{account_id}')],
        [InlineKeyboardButton("◀️ Назад", callback_data='my_accounts')]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

# ==================== ADMIN HANDLERS ====================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Доступ запрещён")
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить аккаунт", callback_data='admin_add')],
        [InlineKeyboardButton("💰 Выдать баланс", callback_data='admin_balance')],
        [InlineKeyboardButton("📋 Все аккаунты", callback_data='admin_list')],
        [InlineKeyboardButton("🔐 Запросить код", callback_data='admin_request_code')]
    ]
    
    await update.message.reply_text("⚙️ <b>Админ-панель</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📝 Отправь: ИМЯ | ТЕЛЕФОН | ЦЕНА\nПример: VIP | +79991234567 | 5000")
    context.user_data['mode'] = 'add_account'

async def admin_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("💰 Отправь: USER_ID СУММА\nПример: 123456789 5000")
    context.user_data['mode'] = 'give_balance'

async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    
    db = get_session()
    accounts = db.query(Account).all()
    db.close()
    
    if not accounts:
        await query.edit_message_text("📭 Нет аккаунтов")
        return
    
    text = "📋 <b>Все аккаунты:</b>\n\n"
    for acc in accounts:
        status = "✅" if acc.sold else "🟢"
        text += f"{status} {acc.name} | {acc.phone} | {acc.price}{CURRENCY}\n"
    
    await query.edit_message_text(text, parse_mode='HTML')

async def admin_request_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📱 Отправь номер телефона: +79991234567")
    context.user_data['mode'] = 'request_code'

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    mode = context.user_data.get('mode')
    text = update.message.text
    
    if mode == 'add_account':
        try:
            parts = text.split('|')
            name = parts[0].strip()
            phone = parts[1].strip()
            price = float(parts[2].strip())
            
            db = get_session()
            account = Account(name=name, phone=phone, price=price, owner_id=ADMIN_ID)
            db.add(account)
            db.commit()
            db.close()
            
            await update.message.reply_text(f"✅ Добавлено: {name}")
            context.user_data['mode'] = None
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")
    
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
                await update.message.reply_text(f"✅ +{amount}{CURRENCY} выдано")
            else:
                await update.message.reply_text("❌ Юзер не найден")
            db.close()
            context.user_data['mode'] = None
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")
    
    elif mode == 'request_code':
        try:
            phone = text.strip()
            if not phone.startswith('+'):
                await update.message.reply_text("❌ Формат: +7XXXXXXXXXX")
                return
            
            account_id = hash(phone) % 1000000
            success, message = await telethon_mgr.request_code(phone, account_id)
            
            if success:
                await update.message.reply_text(f"✅ {message}\n\n📝 Отправь код")
                context.user_data['pending_phone'] = phone
                context.user_data['pending_account_id'] = account_id
                context.user_data['mode'] = 'verify_code'
            else:
                await update.message.reply_text(f"❌ {message}")
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")
    
    elif mode == 'verify_code':
        try:
            phone = context.user_data.get('pending_phone')
            account_id = context.user_data.get('pending_account_id')
            
            if text.lower() == '2fa':
                await update.message.reply_text("🔐 Отправь пароль 2FA")
                context.user_data['mode'] = 'verify_2fa'
                return
            
            if not text.isdigit() or len(text) != 5:
                await update.message.reply_text("❌ Код должен быть 5 цифр")
                return
            
            success, message = await telethon_mgr.verify_code(phone, text)
            
            if success:
                await update.message.reply_text(f"✅ {message}\n\n📝 Отправь имя для аккаунта")
                context.user_data['mode'] = 'account_name'
                context.user_data['verified_phone'] = phone
            elif message == "2FA_REQUIRED":
                await update.message.reply_text("🔐 Отправь пароль 2FA")
                context.user_data['mode'] = 'verify_2fa'
            else:
                await update.message.reply_text(f"❌ {message}")
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")
    
    elif mode == 'verify_2fa':
        try:
            phone = context.user_data.get('pending_phone')
            success, message = await telethon_mgr.verify_2fa(phone, text)
            
            if success:
                await update.message.reply_text(f"✅ {message}\n\n📝 Отправь имя для аккаунта")
                context.user_data['mode'] = 'account_name'
                context.user_data['verified_phone'] = phone
            else:
                await update.message.reply_text(f"❌ {message}")
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")
    
    elif mode == 'account_name':
        try:
            name = text.strip()
            phone = context.user_data.get('verified_phone')
            
            db = get_session()
            account = Account(name=name, phone=phone, price=0, owner_id=ADMIN_ID)
            db.add(account)
            db.commit()
            db.close()
            
            await update.message.reply_text(f"✅ Аккаунт добавлен: {name}\n📱 {phone}\n📡 Слушаю коды...")
            context.user_data['mode'] = None
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")

async def back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🛍️ Магазин", callback_data='shop')],
        [InlineKeyboardButton("💰 Профиль", callback_data='profile')],
        [InlineKeyboardButton(f"💬 Поддержка ({ADMIN_USERNAME})", url=f'https://t.me/{ADMIN_USERNAME.replace("@", "")}')]
    ]
    
    await query.edit_message_text(
        f"👋 {SHOP_NAME}\n\n🎁 Продажа физических аккаунтов",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

def main():
    logger.info("🚀 Starting bot...")
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('admin', admin))
    
    app.add_handler(CallbackQueryHandler(shop, pattern='shop'))
    app.add_handler(CallbackQueryHandler(profile, pattern='profile'))
    app.add_handler(CallbackQueryHandler(my_accounts, pattern='my_accounts'))
    app.add_handler(CallbackQueryHandler(get_code, pattern='get_code_'))
    app.add_handler(CallbackQueryHandler(buy, pattern='buy_'))
    app.add_handler(CallbackQueryHandler(admin_add, pattern='admin_add'))
    app.add_handler(CallbackQueryHandler(admin_balance, pattern='admin_balance'))
    app.add_handler(CallbackQueryHandler(admin_list, pattern='admin_list'))
    app.add_handler(CallbackQueryHandler(admin_request_code, pattern='admin_request_code'))
    app.add_handler(CallbackQueryHandler(back, pattern='back'))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    logger.info("✅ Ready")
    app.run_polling()

if __name__ == '__main__':
    main()
