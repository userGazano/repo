import logging
import re
import os
from datetime import datetime, timedelta
from typing import Optional, Tuple
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, FloodWaitError

logger = logging.getLogger(__name__)

class TelethonManager:
    def __init__(self, api_id: int, api_hash: str, sessions_dir: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.sessions_dir = sessions_dir
        self.clients = {}
        self.pending_auth = {}
        self.captured_codes = {}
    
    def get_session_path(self, phone: str) -> str:
        clean_phone = phone.replace('+', '').replace(' ', '')
        return os.path.join(self.sessions_dir, f"account_{clean_phone}")
    
    async def request_code(self, account_id: int, phone: str) -> Tuple[bool, str]:
        try:
            logger.info(f"🔐 Запрашиваю код для {phone}")
            
            session_path = self.get_session_path(phone)
            client = TelegramClient(session_path, self.api_id, self.api_hash)
            await client.connect()
            
            if await client.is_user_authorized():
                logger.info(f"✅ Уже авторизован")
                self.clients[account_id] = client
                self.captured_codes[account_id] = {'code': None, 'expires_at': None}
                await self._start_listening(account_id, client)
                return True, "Уже авторизован"
            
            result = await client.send_code_request(phone)
            phone_code_hash = result.phone_code_hash
            
            self.pending_auth[phone] = {
                'account_id': account_id,
                'client': client,
                'phone_code_hash': phone_code_hash,
            }
            
            logger.info(f"📨 Код отправлен")
            return True, "Код отправлен на номер"
            
        except FloodWaitError as e:
            return False, f"Флуд. Жди {e.seconds}с"
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            return False, str(e)
    
    async def verify_code(self, phone: str, code: str) -> Tuple[bool, str]:
        if phone not in self.pending_auth:
            return False, "Нет ожидающего кода"
        
        try:
            auth_data = self.pending_auth[phone]
            client = auth_data['client']
            phone_code_hash = auth_data['phone_code_hash']
            account_id = auth_data['account_id']
            
            logger.info(f"🔐 Проверяю код для {phone}")
            
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            logger.info(f"✅ Вход успешен {phone}")
            
            me = await client.get_me()
            
            self.clients[account_id] = client
            del self.pending_auth[phone]
            self.captured_codes[account_id] = {'code': None, 'expires_at': None}
            await self._start_listening(account_id, client)
            
            return True, f"Вход выполнен! {me.first_name}"
            
        except SessionPasswordNeededError:
            return False, "2FA_REQUIRED"
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            return False, str(e)
    
    async def verify_2fa(self, phone: str, password: str) -> Tuple[bool, str]:
        if phone not in self.pending_auth:
            return False, "Нет ожидающего кода"
        
        try:
            auth_data = self.pending_auth[phone]
            client = auth_data['client']
            account_id = auth_data['account_id']
            
            logger.info(f"🔐 Проверка 2FA для {phone}")
            await client.sign_in(password=password)
            
            self.clients[account_id] = client
            del self.pending_auth[phone]
            self.captured_codes[account_id] = {'code': None, 'expires_at': None}
            await self._start_listening(account_id, client)
            
            return True, "2FA ОК!"
            
        except Exception as e:
            logger.error(f"Ошибка 2FA: {e}")
            return False, str(e)
    
    async def _start_listening(self, account_id: int, client: TelegramClient):
        @client.on(events.NewMessage(incoming=True))
        async def on_message(event):
            try:
                text = event.message.message
                if not text:
                    return
                
                code = self._extract_code(text)
                if code:
                    logger.info(f"🎯 КОД ПЕРЕХВАЧЕН: {code} (account {account_id})")
                    self.captured_codes[account_id] = {
                        'code': code,
                        'expires_at': datetime.now() + timedelta(minutes=10)
                    }
            except Exception as e:
                logger.error(f"Ошибка: {e}")
        
        logger.info(f"📡 Слушаю аккаунт {account_id}")
    
    def _extract_code(self, text: str) -> Optional[str]:
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
    
    def get_code(self, account_id: int) -> Optional[str]:
        """Получить перехваченный код"""
        if account_id not in self.captured_codes:
            return None
        
        data = self.captured_codes[account_id]
        if not data['code']:
            return None
        
        if data['expires_at'] < datetime.now():
            self.captured_codes[account_id]['code'] = None
            return None
        
        return data['code']
    
    async def disconnect(self, account_id: int):
        if account_id in self.clients:
            await self.clients[account_id].disconnect()
            del self.clients[account_id]
