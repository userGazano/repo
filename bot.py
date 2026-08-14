# bot.py — ПОЛНЫЙ КОД С ИНТЕГРАЦИЕЙ ENIVVV

import os
import logging
import random
from pathlib import Path
from datetime import datetime
from config import (
    BOT_TOKEN, ADMIN_ID, ADMIN_USERNAME, SHOP_NAME, CURRENCY,
    TELEGRAM_API_ID, TELEGRAM_API_HASH
)
from database import get_session, User, Category, Account, UserAccount, Transaction
from telethon_manager import TelethonManager

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes,
    CallbackQueryHandler, ConversationHandler
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

# Состояния для добавления аккаунта
(AUTH_PHONE, AUTH_CODE, AUTH_2FA, SELECT_CATEGORY) = range(4)

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
    
    db = get_session()
    user_obj = db.query(User).filter_by(telegram_id=user_id).first()
    user_obj.balance -= cat.price
    
    account_obj = db.query(Account).filter_by(id=account.id).first()
    account_obj.available = False
    account_obj.sold_to = user_id
    
    user_account = UserAccount(user_id=user_id, account_id=account.id)
    transaction = Transaction(user_id=user_id, type='purchase', amount=cat.price)
    
    db.add(user_account)
    db.add(transaction)
    db.commit()
    db.close()
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='shop')]]
    await query.edit_message_text(
        f"✅ <b>Куплено!</b>\n\n{cat.emoji} {cat.name}\n📱 {account.phone}\n\n💰 Баланс: {user_obj.balance}⭐️",
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
        keyboard.append([InlineKeyboardButton(f"📨 Получить код: {account.phone}", callback_data=f'get_code_{account.id}')])
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
        text = f"✅ <b>КОД:</b>\n\n<code>{code}</code>\n\n⏱️ Действует 10 минут"
    else:
        text = f"⏳ <b>Ожидание кода...</b>\n\n📱 {account.phone}\n\nПроверьте входящие СМС в Telegram"
    
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
        [InlineKeyboardButton("📂 Категории", callback_data='admin_categories')],
        [InlineKeyboardButton("⭐️ Выдать баланс", callback_data='admin_balance')],
        [InlineKeyboardButton("📱 Выдать аккаунт", callback_data='admin_give_account')],
        [InlineKeyboardButton("📋 Все аккаунты", callback_data='admin_list')]
    ]
    
    await update.message.reply_text("⚙️ <b>Админ</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def admin_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.callback_query.answer("❌ Доступ запрещён", show_alert=True)
        return ConversationHandler.END
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📱 <b>Введи номер телефона</b>\n\nПример: +79991234567",
        parse_mode='HTML'
    )
    return AUTH_PHONE

async def admin_receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    
    phone = update.message.text.strip()
    
    if not phone.startswith('+') or len(phone) < 10:
        await update.message.reply_text("❌ Неверный формат. Попробуй: +79991234567")
        return AUTH_PHONE
    
    context.user_data['phone'] = phone
    context.user_data['account_id'] = hash(phone) % 1000000
    
    await update.message.reply_text("⏳ Отправляю код...")
    success, message = await telethon_mgr.request_code(phone, context.user_data['account_id'])
    
    if success:
        await update.message.reply_text(f"✅ {message}\n\n📝 Введи 5-значный код", parse_mode='HTML')
        return AUTH_CODE
    else:
        await update.message.reply_text(f"❌ {message}")
        return ConversationHandler.END

async def admin_receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    
    code = update.message.text.strip()
    
    if not code.isdigit() or len(code) != 5:
        await update.message.reply_text("❌ Код должен быть 5 цифр")
        return AUTH_CODE
    
    phone = context.user_data['phone']
    
    await update.message.reply_text("⏳ Проверяю...")
    success, message = await telethon_mgr.verify_code(phone, code)
    
    if success:
        await update.message.reply_text(f"✅ {message}\n\n📂 Выбери категорию", parse_mode='HTML')
        db = get_session()
        categories = db.query(Category).all()
        db.close()
        
        keyboard = []
        for cat in categories:
            keyboard.append([InlineKeyboardButton(f"{cat.emoji} {cat.name} ({cat.price}⭐️)", callback_data=f'admin_cat_{cat.id}')])
        
        await update.message.reply_text(
            "📂 <b>Выбери категорию:</b>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        return SELECT_CATEGORY
    elif message == "2FA_REQUIRED":
        await update.message.reply_text("🔐 Введи пароль 2FA:", parse_mode='HTML')
        return AUTH_2FA
    else:
        await update.message.reply_text(f"❌ {message}")
        return ConversationHandler.END

async def admin_receive_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    
    password = update.message.text.strip()
    phone = context.user_data['phone']
    
    await update.message.reply_text("⏳ Проверяю...")
    success, message = await telethon_mgr.verify_2fa(phone, password)
    
    if success:
        await update.message.reply_text(f"✅ {message}\n\n📂 Выбери категорию", parse_mode='HTML')
        db = get_session()
        categories = db.query(Category).all()
        db.close()
        
        keyboard = []
        for cat in categories:
            keyboard.append([InlineKeyboardButton(f"{cat.emoji} {cat.name} ({cat.price}⭐️)", callback_data=f'admin_cat_{cat.id}')])
        
        await update.message.reply_text(
            "📂 <b>Выбери категорию:</b>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        return SELECT_CATEGORY
    else:
        await update.message.reply_text(f"❌ {message}")
        return ConversationHandler.END

async def admin_select_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    
    query = update.callback_query
    await query.answer()
    
    category_id = int(query.data.split('_')[2])
    phone = context.user_data['phone']
    account_id = context.user_data['account_id']
    
    db = get_session()
    cat = db.query(Category).filter_by(id=category_id).first()
    
    if not cat:
        await query.edit_message_text("❌ Категория не найдена")
        db.close()
        return ConversationHandler.END
    
    account = Account(category_id=category_id, phone=phone)
    db.add(account)
    db.commit()
    db.close()
    
    await query.edit_message_text(
        f"✅ <b>Аккаунт добавлен!</b>\n\n{cat.emoji} {cat.name}\n📱 {phone}\n\n📡 Слушаю входящие коды...",
        parse_mode='HTML'
    )
    context.user_data.clear()
    return ConversationHandler.END

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
        db = get_session()
        for cat in categories:
            accounts_count = db.query(Account).filter_by(category_id=cat.id, available=True).count()
            text += f"{cat.emoji} {cat.name} - {cat.price}⭐️ ({accounts_count} акк)\n"
        db.close()
    
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
    
    if not accounts:
        await query.edit_message_text("📭 Нет аккаунтов")
        return
    
    text = "📋 <b>Все аккаунты:</b>\n\n"
    for acc in accounts:
        status = "✅ ПРОДАН" if not acc.available else "🟢 ДОСТУПЕН"
        text += f"{status} - {acc.phone}\n"
    
    await query.edit_message_text(text, parse_mode='HTML')

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    mode = context.user_data.get('mode')
    text = update.message.text
    
    if mode == 'new_category':
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
            account = db.query(Account).filter_by(category_id=category_id, available=True).first()
            if not account:
                await update.message.reply_text("❌ Нет доступных аккаунтов в этой категории")
                db.close()
                return
            
            account.available = False
            account.sold_to = user_id
            user_account = UserAccount(user_id=user_id, account_id=account.id)
            db.add(user_account)
            db.commit()
            db.close()
            
            await update.message.reply_text(f"✅ Аккаунт выдан\n\n📱 {account.phone}")
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
    
    # Conversation handler для добавления аккаунта админом
    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_start, pattern='admin_add')],
        states={
            AUTH_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_phone)],
            AUTH_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_code)],
            AUTH_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_2fa)],
            SELECT_CATEGORY: [CallbackQueryHandler(admin_select_category, pattern='admin_cat_')],
        },
        fallbacks=[CommandHandler('cancel', lambda u, c: ConversationHandler.END)],
    )
    
    # Handlers
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
    
    app.add_handler(add_conv)
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
