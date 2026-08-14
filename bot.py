import os
import logging
import random
from pathlib import Path
from datetime import datetime
from config import BOT_TOKEN, ADMIN_ID, ADMIN_USERNAME, SHOP_NAME, CURRENCY, TELEGRAM_API_ID, TELEGRAM_API_HASH
from database import get_session, User, Category, Account, UserAccount, Transaction
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
        f"👋 Добро пожаловать в <b>{SHOP_NAME}</b>\n\n🎁 Продажа аккаунтов",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    db = get_session()
    categories = db.query(Category).all()
    db.close()
    
    if not categories:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back')]]
        await query.edit_message_text("📭 Нет категорий", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    text = f"🛍️ <b>Магазин</b>\n\n"
    keyboard = []
    
    for cat in categories:
        text += f"{cat.emoji} {cat.name} — {cat.price}⭐️\n"
        keyboard.append([InlineKeyboardButton(f"{cat.emoji} {cat.name}", callback_data=f'cat_{cat.id}')])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='back')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    category_id = int(query.data.split('_')[1])
    db = get_session()
    
    cat = db.query(Category).filter_by(id=category_id).first()
    accounts = db.query(Account).filter_by(category_id=category_id, available=True).all()
    db.close()
    
    if not accounts:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='shop')]]
        await query.edit_message_text("❌ Нет доступных аккаунтов", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    text = f"{cat.emoji} <b>{cat.name}</b>\n\n📱 Доступно: {len(accounts)}\n💰 Цена: {cat.price}⭐️"
    
    keyboard = [
        [InlineKeyboardButton(f"💳 Купить за {cat.price}⭐️", callback_data=f'buy_cat_{category_id}')],
        [InlineKeyboardButton("◀️ Назад", callback_data='shop')]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def buy_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    category_id = int(query.data.split('_')[2])
    user_id = query.from_user.id
    
    db = get_session()
    user = db.query(User).filter_by(telegram_id=user_id).first()
    cat = db.query(Category).filter_by(id=category_id).first()
    accounts = db.query(Account).filter_by(category_id=category_id, available=True).all()
    db.close()
    
    if not accounts:
        await query.edit_message_text("❌ Нет доступных аккаунтов")
        return
    
    if user.balance < cat.price:
        await query.edit_message_text(
            f"❌ Мало звёзд\n\n💰 Баланс: {user.balance}⭐️\n💳 Нужно: {cat.price}⭐️"
        )
        return
    
    account = random.choice(accounts)
    
    user.balance -= cat.price
    account.available = False
    account.sold_to = user_id
    
    user_account = UserAccount(user_id=user_id, account_id=account.id)
    transaction = Transaction(user_id=user_id, type='purchase', amount=cat.price)
    
    db = get_session()
    db.add(user_account)
    db.add(transaction)
    user_obj = db.query(User).filter_by(telegram_id=user_id).first()
    user_obj.balance -= cat.price
    db.commit()
    db.close()
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='shop')]]
    await query.edit_message_text(
        f"✅ <b>Куплено!</b>\n\n{cat.emoji} {cat.name}\n📱 {account.phone}\n\n💰 Баланс: {user.balance}⭐️",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    db = get_session()
    user = db.query(User).filter_by(telegram_id=query.from_user.id).first()
    accounts_count = db.query(UserAccount).filter_by(user_id=query.from_user.id).count()
    db.close()
    
    text = (
        f"👤 <b>Профиль @{user.username or 'unknown'}</b>\n\n"
        f"🆔 ID: {user.telegram_id}\n"
        f"⭐️ Баланс: {user.balance}⭐️\n"
        f"📅 Дата регистрации: {user.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        f"✅ Активен\n"
        f"📱 Аккаунтов: {accounts_count}"
    )
    
    keyboard = [
        [InlineKeyboardButton("⭐️ Пополнить баланс", callback_data='top_up')],
        [InlineKeyboardButton("📱 Мои аккаунты", callback_data='my_accounts')],
        [InlineKeyboardButton("◀️ Назад", callback_data='back')]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def top_up(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("100⭐️", callback_data='topup_100')],
        [InlineKeyboardButton("500⭐️", callback_data='topup_500')],
        [InlineKeyboardButton("1000⭐️", callback_data='topup_1000')],
        [InlineKeyboardButton("◀️ Назад", callback_data='profile')]
    ]
    
    await query.edit_message_text(
        "⭐️ <b>Пополнить баланс</b>\n\nВыбери количество звёзд:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def topup_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    amount = int(query.data.split('_')[1])
    
    await query.edit_message_text(
        f"⭐️ <b>Подтвердите покупку</b>\n\n"
        f"Вы покупаете: {amount}⭐️\n\n"
        f"<i>Нажмите кнопку ниже для оплаты звёздами Telegram</i>",
        parse_mode='HTML'
    )

async def my_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    db = get_session()
    user_accounts = db.query(UserAccount).filter_by(user_id=query.from_user.id).all()
    db.close()
    
    if not user_accounts:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='profile')]]
        await query.edit_message_text("📭 Нет аккаунтов", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    text = f"📱 <b>Мои аккаунты ({len(user_accounts)})</b>\n\n"
    keyboard = []
    
    db = get_session()
    for ua in user_accounts:
        account = db.query(Account).filter_by(id=ua.account_id).first()
        cat = db.query(Category).filter_by(id=account.category_id).first()
        text += f"{cat.emoji} {cat.name}\n📱 {account.phone}\n\n"
        keyboard.append([InlineKeyboardButton(f"📨 Код: {account.phone}", callback_data=f'get_code_{account.id}')])
    db.close()
    
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
        await query.edit_message_text("❌ Не найден")
        return
    
    code = telethon_mgr.get_code(account_id)
    
    if code:
        text = f"✅ <b>КОД:</b>\n\n<code>{code}</code>\n\n⏱️ 10 минут"
    else:
        text = f"⏳ <b>Ожидание...</b>\n\n📱 {account.phone}\n\nПроверь СМС"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data=f'get_code_{account_id}')],
        [InlineKeyboardButton("◀️ Назад", callback_data='my_accounts')]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

# ==================== ADMIN ====================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Доступ запрещён")
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить аккаунт", callback_data='admin_add')],
        [InlineKeyboardButton("📂 Категории", callback_data='admin_categories')],
        [InlineKeyboardButton("⭐️ Выдать баланс", callback_data='admin_balance')],
        [InlineKeyboardButton("📱 Выдать аккаунт", callback_data='admin_give_account')],
        [InlineKeyboardButton("📋 Все аккаунты", callback_data='admin_list')]
    ]
    
    await update.message.reply_text("⚙️ <b>Админ</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📱 Отправь номер: +79991234567")
    context.user_data['mode'] = 'request_code'

async def admin_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    
    db = get_session()
    categories = db.query(Category).all()
    db.close()
    
    text = "📂 <b>Категории:</b>\n\n"
    keyboard = []
    
    if categories:
        for cat in categories:
            accounts_count = db.query(Account).filter_by(category_id=cat.id, available=True).count()
            text += f"{cat.emoji} {cat.name} - {cat.price}⭐️ ({accounts_count} акк)\n"
    
    keyboard.append([InlineKeyboardButton("➕ Новая категория", callback_data='admin_new_cat')])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='admin_back')])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def admin_new_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📝 Отправь: ЭМОДЗИ НАЗВАНИЕ ЦЕНА\nПример: 🇺🇸 USA 50")
    context.user_data['mode'] = 'new_category'

async def admin_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⭐️ Отправь: USER_ID КОЛИЧЕСТВО\nПример: 123456789 500")
    context.user_data['mode'] = 'give_balance'

async def admin_give_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📱 Отправь: USER_ID CATEGORY_ID\nПример: 123456789 1")
    context.user_data['mode'] = 'give_account'

async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    
    db = get_session()
    accounts = db.query(Account).all()
    db.close()
    
    text = "📋 <b>Все аккаунты:</b>\n\n"
    for acc in accounts:
        status = "✅" if not acc.available else "🟢"
        text += f"{status} {acc.phone}\n"
    
    await query.edit_message_text(text, parse_mode='HTML')

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    mode = context.user_data.get('mode')
    text = update.message.text
    
    if mode == 'request_code':
        try:
            phone = text.strip()
            account_id = hash(phone) % 1000000
            success, message = await telethon_mgr.request_code(phone, account_id)
            
            if success:
                await update.message.reply_text(f"✅ Код отправлен\n\n📝 Отправь код")
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
            
            if text.lower() == '2fa':
                await update.message.reply_text("🔐 Пароль 2FA:")
                context.user_data['mode'] = 'verify_2fa'
                return
            
            success, message = await telethon_mgr.verify_code(phone, text)
            
            if success:
                await update.message.reply_text(f"✅ Верно\n\n📂 Отправь категорию\nПример: 1")
                context.user_data['mode'] = 'select_category'
                context.user_data['verified_phone'] = phone
            elif message == "2FA_REQUIRED":
                await update.message.reply_text("🔐 Пароль 2FA:")
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
                await update.message.reply_text(f"✅ ОК\n\n📂 Категория ID:")
                context.user_data['mode'] = 'select_category'
                context.user_data['verified_phone'] = phone
            else:
                await update.message.reply_text(f"❌ {message}")
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")
    
    elif mode == 'select_category':
        try:
            category_id = int(text)
            phone = context.user_data.get('verified_phone')
            
            db = get_session()
            cat = db.query(Category).filter_by(id=category_id).first()
            if not cat:
                await update.message.reply_text("❌ Категория не найдена")
                db.close()
                return
            
            account = Account(category_id=category_id, phone=phone)
            db.add(account)
            db.commit()
            db.close()
            
            await update.message.reply_text(f"✅ Добавлено\n\n{cat.emoji} {cat.name}\n📱 {phone}")
            context.user_data['mode'] = None
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")
    
    elif mode == 'new_category':
        try:
            parts = text.split()
            emoji = parts[0]
            name = parts[1]
            price = float(parts[2])
            
            db = get_session()
            category = Category(emoji=emoji, name=name, price=price)
            db.add(category)
            db.commit()
            db.close()
            
            await update.message.reply_text(f"✅ Категория создана\n\n{emoji} {name} - {price}⭐️")
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
                await update.message.reply_text(f"✅ +{amount}⭐️")
            else:
                await update.message.reply_text("❌ Не найден")
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
            account = db.query(Account).filter_by(category_id=category_id, available=True).first()
            if not account:
                await update.message.reply_text("❌ Нет доступных")
                db.close()
                return
            
            account.available = False
            account.sold_to = user_id
            user_account = UserAccount(user_id=user_id, account_id=account.id)
            db.add(user_account)
            db.commit()
            db.close()
            
            await update.message.reply_text(f"✅ Выдано\n\n📱 {account.phone}")
            context.user_data['mode'] = None
        except Exception as e:
            await update.message.reply_text(f"❌ {e}")

async def admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    await admin(update, context)

async def back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🛍️ Магазин", callback_data='shop')],
        [InlineKeyboardButton("💰 Профиль", callback_data='profile')],
        [InlineKeyboardButton(f"💬 Поддержка ({ADMIN_USERNAME})", url=f'https://t.me/{ADMIN_USERNAME.replace("@", "")}')]
    ]
    
    await query.edit_message_text(
        f"👋 {SHOP_NAME}",
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
    app.add_handler(CallbackQueryHandler(category, pattern='cat_'))
    app.add_handler(CallbackQueryHandler(buy_category, pattern='buy_cat_'))
    app.add_handler(CallbackQueryHandler(top_up, pattern='top_up'))
    app.add_handler(CallbackQueryHandler(topup_amount, pattern='topup_'))
    app.add_handler(CallbackQueryHandler(my_accounts, pattern='my_accounts'))
    app.add_handler(CallbackQueryHandler(get_code, pattern='get_code_'))
    
    app.add_handler(CallbackQueryHandler(admin_add, pattern='admin_add'))
    app.add_handler(CallbackQueryHandler(admin_categories, pattern='admin_categories'))
    app.add_handler(CallbackQueryHandler(admin_new_cat, pattern='admin_new_cat'))
    app.add_handler(CallbackQueryHandler(admin_balance, pattern='admin_balance'))
    app.add_handler(CallbackQueryHandler(admin_give_account, pattern='admin_give_account'))
    app.add_handler(CallbackQueryHandler(admin_list, pattern='admin_list'))
    app.add_handler(CallbackQueryHandler(admin_back, pattern='admin_back'))
    app.add_handler(CallbackQueryHandler(back, pattern='back'))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    logger.info("✅ Ready")
    app.run_polling()

if __name__ == '__main__':
    main()
