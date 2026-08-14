import os
import logging
from pathlib import Path
from datetime import datetime
from config import BOT_TOKEN, ADMIN_ID, ADMIN_USERNAME, SHOP_NAME, CURRENCY
from database import init_db, get_session, User, Account, Transaction
from telethon_manager import telethon_mgr

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

init_db()

(AUTH_PHONE, AUTH_CODE, AUTH_2FA) = range(3)

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

# ==================== HANDLERS ====================

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
        [InlineKeyboardButton("💰 Мой профиль", callback_data='profile')],
        [InlineKeyboardButton(f"💬 Поддержка ({ADMIN_USERNAME})", url=f'https://t.me/{ADMIN_USERNAME.replace("@", "")}')]
    ]
    
    await update.message.reply_text(
        f"👋 Добро пожаловать в <b>{SHOP_NAME}</b>\n\n"
        "Продажа физических аккаунтов Telegram",
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
        await query.edit_message_text(
            "📭 Нет доступных аккаунтов",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    text = f"🛍️ <b>Магазин — Физические аккаунты</b>\n\n"
    keyboard = []
    
    for acc in accounts:
        text += f"📱 {acc.name}\n💵 {acc.price}{CURRENCY}\n\n"
        keyboard.append([InlineKeyboardButton(f"Купить: {acc.name}", callback_data=f'buy_{acc.id}')])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='back')])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def buy_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    account_id = int(query.data.split('_')[1])
    
    db = get_session()
    account = db.query(Account).filter_by(id=account_id, sold=False).first()
    
    if not account:
        await query.edit_message_text("❌ Аккаунт недоступен")
        db.close()
        return
    
    user = db.query(User).filter_by(telegram_id=query.from_user.id).first()
    
    if user.balance < account.price:
        await query.edit_message_text(
            f"❌ Недостаточно средств\n"
            f"Баланс: {user.balance}{CURRENCY}\n"
            f"Нужно: {account.price}{CURRENCY}"
        )
        db.close()
        return
    
    # Списываем баланс
    user.balance -= account.price
    account.sold = True
    account.sold_to = query.from_user.id
    account.sold_at = datetime.now()
    
    # Создаём транзакцию
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
        f"✅ <b>Покупка успешна!</b>\n\n"
        f"📱 {account.name}\n"
        f"📱 {account.phone}\n\n"
        f"Аккаунт передан в ваш профиль",
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
    
    text = f"👤 <b>Мой профиль</b>\n\n"
    text += f"💰 Баланс: {user.balance}{CURRENCY}\n"
    text += f"📱 Аккаунтов: {len(accounts)}\n\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back')]]
    
    if accounts:
        text += "<b>Мои аккаунты:</b>\n"
        for acc in accounts:
            text += f"📱 {acc.name} — {acc.phone}\n"
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🛍️ Магазин", callback_data='shop')],
        [InlineKeyboardButton("💰 Мой профиль", callback_data='profile')],
        [InlineKeyboardButton(f"💬 Поддержка ({ADMIN_USERNAME})", url=f'https://t.me/{ADMIN_USERNAME.replace("@", "")}')]
    ]
    
    await query.edit_message_text(
        f"👋 {SHOP_NAME}\n\nПродажа физических аккаунтов Telegram",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

# ==================== ADMIN PANEL ====================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Access denied")
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить аккаунт", callback_data='admin_add_account')],
        [InlineKeyboardButton("📋 Все аккаунты", callback_data='admin_list_accounts')],
        [InlineKeyboardButton("💰 Выдать баланс", callback_data='admin_give_balance')],
        [InlineKeyboardButton("🔑 Выдать админку", callback_data='admin_make_admin')],
        [InlineKeyboardButton("📢 Рассылка", callback_data='admin_broadcast')]
    ]
    
    await update.message.reply_text(
        "⚙️ <b>Админ-панель</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def admin_add_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📱 Отправьте данные аккаунта в формате:\nИМЯ | ТЕЛЕФОН | ЦЕНА\n\nПример: VIP Account | +79991234567 | 5000")
    context.user_data['admin_mode'] = 'add_account'

async def admin_list_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    keyboard = []
    
    for acc in accounts:
        status = "✅ ПРОДАН" if acc.sold else "🟢 ДОСТУПЕН"
        text += f"ID {acc.id} | {acc.name} | {acc.phone} | {acc.price}{CURRENCY} | {status}\n"
        if not acc.sold:
            keyboard.append([InlineKeyboardButton(f"Удалить {acc.id}", callback_data=f'admin_delete_{acc.id}')])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='admin_back')])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def admin_give_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("💰 Отправьте: USER_ID СУММА\n\nПример: 123456789 5000")
    context.user_data['admin_mode'] = 'give_balance'

async def admin_make_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔑 Отправьте USER_ID")
    context.user_data['admin_mode'] = 'make_admin'

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📢 Отправьте сообщение для рассылки всем юзерам")
    context.user_data['admin_mode'] = 'broadcast'

async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    mode = context.user_data.get('admin_mode')
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
            
            await update.message.reply_text(f"✅ Аккаунт добавлен: {name}")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
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
                await update.message.reply_text(f"✅ Баланс +{amount}{CURRENCY}")
            else:
                await update.message.reply_text("❌ Юзер не найден")
            db.close()
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    elif mode == 'make_admin':
        try:
            user_id = int(text)
            db = get_session()
            user = db.query(User).filter_by(telegram_id=user_id).first()
            if user:
                user.is_admin = True
                db.commit()
                await update.message.reply_text(f"✅ Юзер {user_id} — админ")
            else:
                await update.message.reply_text("❌ Юзер не найден")
            db.close()
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    elif mode == 'broadcast':
        try:
            db = get_session()
            users = db.query(User).all()
            
            for user in users:
                try:
                    await context.bot.send_message(user.telegram_id, text, parse_mode='HTML')
                except:
                    pass
            
            await update.message.reply_text(f"✅ Отправлено {len(users)} юзерам")
            db.close()
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    context.user_data['admin_mode'] = None

# ==================== MAIN ====================

def main():
    logger.info("🚀 Bot starting...")
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('admin', admin_panel))
    
    app.add_handler(CallbackQueryHandler(shop, pattern='shop'))
    app.add_handler(CallbackQueryHandler(profile, pattern='profile'))
    app.add_handler(CallbackQueryHandler(back_to_main, pattern='back'))
    app.add_handler(CallbackQueryHandler(buy_account, pattern='buy_'))
    
    app.add_handler(CallbackQueryHandler(admin_add_account, pattern='admin_add_account'))
    app.add_handler(CallbackQueryHandler(admin_list_accounts, pattern='admin_list_accounts'))
    app.add_handler(CallbackQueryHandler(admin_give_balance, pattern='admin_give_balance'))
    app.add_handler(CallbackQueryHandler(admin_make_admin, pattern='admin_make_admin'))
    app.add_handler(CallbackQueryHandler(admin_broadcast, pattern='admin_broadcast'))
    app.add_handler(CallbackQueryHandler(back_to_main, pattern='admin_back'))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_input))
    
    logger.info("✅ Ready")
    app.run_polling()

if __name__ == '__main__':
    main()
