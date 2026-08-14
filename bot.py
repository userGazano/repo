import os
import logging
from pathlib import Path
from datetime import datetime
from config import BOT_TOKEN, ADMIN_ID, ADMIN_USERNAME, SHOP_NAME, CURRENCY
from database import get_session, User, Account, Transaction

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

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

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
    
    text = f"👤 <b>Профиль</b>\n💰 {user.balance}{CURRENCY}\n📱 Аккаунтов: {len(accounts)}\n"
    
    if accounts:
        text += "\n<b>Мои аккаунты:</b>\n"
        for acc in accounts:
            text += f"📱 {acc.name} — {acc.phone}\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Доступ запрещён")
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить аккаунт", callback_data='admin_add')],
        [InlineKeyboardButton("💰 Выдать баланс", callback_data='admin_balance')],
        [InlineKeyboardButton("📋 Аккаунты", callback_data='admin_list')]
    ]
    
    await update.message.reply_text("⚙️ <b>Админ</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Отправь: ИМЯ | ТЕЛЕФОН | ЦЕНА\nПример: VIP | +79991234567 | 5000")
    context.user_data['mode'] = 'add_account'

async def admin_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Отправь: USER_ID СУММА\nПример: 123456789 5000")
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
    
    text = "📋 <b>Аккаунты:</b>\n\n"
    for acc in accounts:
        status = "✅" if acc.sold else "🟢"
        text += f"{status} {acc.name} | {acc.phone} | {acc.price}{CURRENCY}\n"
    
    await query.edit_message_text(text, parse_mode='HTML')

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
                await update.message.reply_text(f"✅ +{amount}{CURRENCY}")
            else:
                await update.message.reply_text("❌ Не найден")
            db.close()
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
    app.add_handler(CallbackQueryHandler(buy, pattern='buy_'))
    app.add_handler(CallbackQueryHandler(admin_add, pattern='admin_add'))
    app.add_handler(CallbackQueryHandler(admin_balance, pattern='admin_balance'))
    app.add_handler(CallbackQueryHandler(admin_list, pattern='admin_list'))
    app.add_handler(CallbackQueryHandler(back, pattern='back'))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    logger.info("✅ Ready")
    app.run_polling()

if __name__ == '__main__':
    main()
