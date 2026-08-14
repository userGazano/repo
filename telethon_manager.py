import os
import logging
from typing import Optional, Tuple
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from datetime import datetime, timedelta
import re
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH
from database import get_session, TelethonSession, Account

logger = logging.getLogger(__name__)

class TelethonManager:
    def __init__(self):
        self.clients = {}
        self.pending_auth = {}
        self.captured_codes = {}
    
    async def request_code(self, phone: str, account_id: int) -> Tuple[bool, str]:
        try:
            logger.info(f"🔐 Requesting code for {phone}")
            
            # Восстанавливаем сессию из БД если есть
            db = get_session()
            session_record = db.query(TelethonSession).filter_by(phone=phone).first()
            
            if session_record:
                session_string = session_record.session_string
            else:
                session_string = f"session_{phone.replace('+', '')}"
            
            client = TelegramClient(session_string, TELEGRAM_API_ID, TELEGRAM_API_HASH)
            await client.connect()
            
            if await client.is_user_authorized():
                logger.info(f"✅ Already authorized")
                self.clients[account_id] = client
                self.captured_codes[account_id] = {'code': None, 'expires_at': None}
                self._start_listening(account_id, client)
                db.close()
                return True, "Already authorized"
            
            result = await client.send_code_request(phone)
            phone_code_hash = result.phone_code_hash
            
            self.pending_auth[phone] = {
                'account_id': account_id,
                'client': client,
                'phone_code_hash': phone_code_hash,
            }
            
            logger.info(f"📨 Code sent to {phone}")
            db.close()
            return True, "Code sent"
            
        except FloodWaitError as e:
            return False, f"Flood. Wait {e.seconds}s"
        except Exception as e:
            logger.error(f"Error: {e}")
            return False, str(e)
    
    async def verify_code(self, phone: str, code: str) -> Tuple[bool, str]:
        if phone not in self.pending_auth:
            return False, "No pending code"
        
        try:
            auth_data = self.pending_auth[phone]
            client = auth_data['client']
            phone_code_hash = auth_data['phone_code_hash']
            account_id = auth_data['account_id']
            
            logger.info(f"🔐 Verifying code for {phone}")
            
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            logger.info(f"✅ Signed in {phone}")
            
            me = await client.get_me()
            
            # Сохраняем сессию в БД
            db = get_session()
            session_record = db.query(TelethonSession).filter_by(phone=phone).first()
            if not session_record:
                session_record = TelethonSession(phone=phone, session_string=f"session_{phone.replace('+', '')}")
                db.add(session_record)
            db.commit()
            db.close()
            
            self.clients[account_id] = client
            del self.pending_auth[phone]
            self.captured_codes[account_id] = {'code': None, 'expires_at': None}
            self._start_listening(account_id, client)
            
            return True, f"{me.first_name}"
            
        except SessionPasswordNeededError:
            return False, "2FA_REQUIRED"
        except Exception as e:
            logger.error(f"Error: {e}")
            return False, str(e)
    
    async def verify_2fa(self, phone: str, password: str) -> Tuple[bool, str]:
        if phone not in self.pending_auth:
            return False, "No pending"
        
        try:
            auth_data = self.pending_auth[phone]
            client = auth_data['client']
            account_id = auth_data['account_id']
            
            logger.info(f"🔐 2FA for {phone}")
            await client.sign_in(password=password)
            
            db = get_session()
            session_record = db.query(TelethonSession).filter_by(phone=phone).first()
            if not session_record:
                session_record = TelethonSession(phone=phone, session_string=f"session_{phone.replace('+', '')}")
                db.add(session_record)
            db.commit()
            db.close()
            
            self.clients[account_id] = client
            del self.pending_auth[phone]
            self.captured_codes[account_id] = {'code': None, 'expires_at': None}
            self._start_listening(account_id, client)
            
            return True, "2FA OK"
            
        except Exception as e:
            logger.error(f"2FA error: {e}")
            return False, str(e)
    
    def _start_listening(self, account_id: int, client: TelegramClient):
        @client.on(events.NewMessage(incoming=True))
        async def on_message(event):
            try:
                text = event.message.message
                if not text:
                    return
                
                code = self._extract_code(text)
                if code:
                    logger.info(f"🎯 CODE CAPTURED: {code} (account {account_id})")
                    self.captured_codes[account_id] = {
                        'code': code,
                        'expires_at': datetime.now() + timedelta(minutes=10)
                    }
            except Exception as e:
                logger.error(f"Error: {e}")
        
        logger.info(f"📡 Listening {account_id}")
    
    def _extract_code(self, text: str) -> Optional[str]:
        patterns = [
            r'(?:код|code)[\s:]*(\d{5})',
            r'(\d{5})\s+is\s+your',
            r'telegram[\s:]*(\d{5})',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
    
    def get_code(self, account_id: int) -> Optional[str]:
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

telethon_mgr = TelethonManager()
