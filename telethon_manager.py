# telethon_manager.py — ПОЛНЫЙ КОД С ПЕРЕХВАТОМ КОДОВ

import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from database import get_session, TelethonSession

logger = logging.getLogger(__name__)

class TelethonManager:
    def __init__(self, api_id: int, api_hash: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.clients = {}
        self.pending_auth = {}
        self.captured_codes = {}
    
    def _get_session_path(self, phone: str) -> str:
        clean_phone = phone.replace('+', '').replace(' ', '')
        return f"session_{clean_phone}"
    
    async def request_code(self, phone: str, account_id: int) -> Tuple[bool, str]:
        try:
            logger.info(f"🔐 Requesting code for {phone}")
            
            session_path = self._get_session_path(phone)
            client = TelegramClient(session_path, self.api_id, self.api_hash)
            await client.connect()
            
            if await client.is_user_authorized():
                logger.info(f"✅ Already authorized: {phone}")
                self.clients[account_id] = client
                self.captured_codes[account_id] = {
                    'code': None,
                    'timestamp': None,
                    'expires_at': None
                }
                await self._start_listening(account_id, client)
                return True, "Уже авторизован"
            
            result = await client.send_code_request(phone)
            phone_code_hash = result.phone_code_hash
            
            self.pending_auth[phone] = {
                'account_id': account_id,
                'client': client,
                'phone_code_hash': phone_code_hash,
                'created_at': datetime.now()
            }
            
            logger.info(f"📨 Code sent to {phone}")
            return True, "Код отправлен на номер"
            
        except FloodWaitError as e:
            return False, f"Ожидание {e.seconds}сек"
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return False, str(e)
    
    async def verify_code(self, phone: str, code: str) -> Tuple[bool, str]:
        if phone not in self.pending_auth:
            return False, "Нет ожидающегося кода"
        
        try:
            auth_data = self.pending_auth[phone]
            client = auth_data['client']
            phone_code_hash = auth_data['phone_code_hash']
            account_id = auth_data['account_id']
            
            logger.info(f"🔐 Verifying code for {phone}")
            
            try:
                await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
                logger.info(f"✅ Signed in: {phone}")
                
                me = await client.get_me()
                
                db = get_session()
                session_record = db.query(TelethonSession).filter_by(phone=phone).first()
                if not session_record:
                    session_record = TelethonSession(
                        phone=phone,
                        session_string=self._get_session_path(phone)
                    )
                    db.add(session_record)
                db.commit()
                db.close()
                
                self.clients[account_id] = client
                del self.pending_auth[phone]
                self.captured_codes[account_id] = {
                    'code': None,
                    'timestamp': None,
                    'expires_at': None
                }
                await self._start_listening(account_id, client)
                
                return True, f"✅ {me.first_name}"
                
            except SessionPasswordNeededError:
                logger.info(f"🔐 2FA needed for {phone}")
                return False, "2FA_REQUIRED"
            
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return False, str(e)
    
    async def verify_2fa(self, phone: str, password: str) -> Tuple[bool, str]:
        if phone not in self.pending_auth:
            return False, "Нет ожидающегося запроса"
        
        try:
            auth_data = self.pending_auth[phone]
            client = auth_data['client']
            account_id = auth_data['account_id']
            
            logger.info(f"🔐 2FA for {phone}")
            await client.sign_in(password=password)
            
            me = await client.get_me()
            
            db = get_session()
            session_record = db.query(TelethonSession).filter_by(phone=phone).first()
            if not session_record:
                session_record = TelethonSession(
                    phone=phone,
                    session_string=self._get_session_path(phone)
                )
                db.add(session_record)
            db.commit()
            db.close()
            
            self.clients[account_id] = client
            del self.pending_auth[phone]
            self.captured_codes[account_id] = {
                'code': None,
                'timestamp': None,
                'expires_at': None
            }
            await self._start_listening(account_id, client)
            
            return True, "✅ 2FA OK"
            
        except Exception as e:
            logger.error(f"❌ 2FA error: {e}")
            return False, str(e)
    
    async def _start_listening(self, account_id: int, client: TelegramClient):
        """Слушает входящие сообщения и перехватывает коды"""
        
        @client.on(events.NewMessage(incoming=True, from_users=777000))
        async def on_message(event):
            try:
                text = event.message.message
                if not text:
                    return
                
                logger.info(f"📬 Message from Telegram: {text[:50]}")
                
                code = self._extract_code(text)
                if code:
                    logger.info(f"🎯 CODE CAPTURED: {code} (account {account_id})")
                    self.captured_codes[account_id] = {
                        'code': code,
                        'timestamp': datetime.now(),
                        'expires_at': datetime.now() + timedelta(minutes=10)
                    }
            except Exception as e:
                logger.error(f"❌ Error in listener: {e}")
        
        try:
            await client.get_me()
            logger.info(f"📡 Listening for codes on account {account_id}")
        except Exception as e:
            logger.error(f"❌ Error starting listener: {e}")
    
    def _extract_code(self, text: str) -> Optional[str]:
        """Извлекает 5-значный код из текста"""
        patterns = [
            r'(?:код|code)[\s:]*(\d{5})',
            r'(\d{5})\s+is\s+your',
            r'telegram[\s:]*(\d{5})',
            r'^(\d{5})$',
            r'(\d{5})',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
    
    def get_code(self, account_id: int) -> Optional[str]:
        """Возвращает захваченный код или None"""
        if account_id not in self.captured_codes:
            return None
        
        data = self.captured_codes[account_id]
        if not data['code']:
            return None
        
        if data['expires_at'] and data['expires_at'] < datetime.now():
            self.captured_codes[account_id]['code'] = None
            return None
        
        return data['code']
    
    async def disconnect(self, account_id: int):
        """Отключает клиент"""
        if account_id in self.clients:
            try:
                await self.clients[account_id].disconnect()
                del self.clients[account_id]
                logger.info(f"✅ Disconnected account {account_id}")
            except Exception as e:
                logger.error(f"❌ Error disconnecting: {e}")
