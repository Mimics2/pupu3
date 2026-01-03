import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
from enum import Enum
import aiosqlite
from aiohttp import web

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputMediaPhoto, InputMediaVideo, BotCommand
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from telegram.constants import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = os.getenv('BOT_TOKEN', '7370973281:AAGdnM2SdekWwSF5alb5vnt0UWAN5QZ1dCQ')
ADMIN_ID = int(os.getenv('ADMIN_ID', '6646433980'))
PORT = int(os.getenv('PORT', '8000'))
DATABASE_PATH = os.getenv('DATABASE_PATH', 'scheduler_bot.db')

# Тарифы (по умолчанию)
TARIFFS = {
    "basic": {
        "name": "Базовый",
        "price": 299,
        "channels_limit": 2,
        "posts_per_day": 5,
        "duration_days": 30
    },
    "premium": {
        "name": "Премиум",
        "price": 599,
        "channels_limit": 5,
        "posts_per_day": 20,
        "duration_days": 30
    },
    "vip": {
        "name": "VIP",
        "price": 999,
        "channels_limit": 10,
        "posts_per_day": 50,
        "duration_days": 30
    }
}

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== БАЗА ДАННЫХ ==========
class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        
    async def init_db(self):
        """Инициализация таблиц в базе данных"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    tariff TEXT DEFAULT 'free',
                    subscription_end DATETIME,
                    channels_count INTEGER DEFAULT 0,
                    posts_today INTEGER DEFAULT 0,
                    last_post_date DATE,
                    registered_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id TEXT PRIMARY KEY,
                    channel_name TEXT,
                    user_id INTEGER,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS scheduled_posts (
                    post_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    channel_id TEXT,
                    content_type TEXT,
                    content TEXT,
                    media_path TEXT,
                    scheduled_time DATETIME,
                    status TEXT DEFAULT 'pending',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    tariff TEXT,
                    amount INTEGER,
                    status TEXT,
                    payment_date DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS tariff_prices (
                    tariff_name TEXT PRIMARY KEY,
                    price INTEGER,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS private_channels (
                    tariff_name TEXT PRIMARY KEY,
                    channel_id TEXT,
                    invite_link TEXT,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.commit()
            
            for tariff_name, tariff_data in TARIFFS.items():
                await db.execute('''
                    INSERT OR IGNORE INTO tariff_prices (tariff_name, price)
                    VALUES (?, ?)
                ''', (tariff_name, tariff_data['price']))
            
            await db.commit()
    
    async def add_user(self, user_id: int, username: str, first_name: str, last_name: str = ""):
        """Добавление нового пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name))
            await db.commit()
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Получение информации о пользователе"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def update_user_tariff(self, user_id: int, tariff: str):
        """Обновление тарифа пользователя"""
        subscription_end = datetime.now() + timedelta(days=30)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE users 
                SET tariff = ?, subscription_end = ?
                WHERE user_id = ?
            ''', (tariff, subscription_end.isoformat(), user_id))
            await db.commit()
    
    async def add_channel(self, user_id: int, channel_id: str, channel_name: str):
        """Добавление канала пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            user = await self.get_user(user_id)
            if user:
                tariff = user['tariff']
                channels_limit = TARIFFS.get(tariff, {}).get('channels_limit', 1)
                
                cursor = await db.execute(
                    'SELECT COUNT(*) FROM channels WHERE user_id = ?', 
                    (user_id,)
                )
                count = (await cursor.fetchone())[0]
                
                if count >= channels_limit:
                    return False, "Превышен лимит каналов для вашего тарифа"
            
            await db.execute('''
                INSERT OR REPLACE INTO channels (channel_id, channel_name, user_id)
                VALUES (?, ?, ?)
            ''', (channel_id, channel_name, user_id))
            await db.commit()
            return True, "Канал успешно добавлен"
    
    async def get_user_channels(self, user_id: int) -> List[Dict]:
        """Получение каналов пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                'SELECT * FROM channels WHERE user_id = ?', 
                (user_id,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def add_scheduled_post(self, user_id: int, channel_id: str, content_type: str, 
                                content: str, media_path: str, scheduled_time: datetime):
        """Добавление запланированной публикации"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                INSERT INTO scheduled_posts 
                (user_id, channel_id, content_type, content, media_path, scheduled_time)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, channel_id, content_type, content, media_path, 
                  scheduled_time.isoformat()))
            await db.commit()
            return cursor.lastrowid
    
    async def get_pending_posts(self) -> List[Dict]:
        """Получение ожидающих публикаций"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT * FROM scheduled_posts 
                WHERE status = 'pending' AND scheduled_time <= datetime('now', '+1 hour')
                ORDER BY scheduled_time
            ''')
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def update_post_status(self, post_id: int, status: str):
        """Обновление статуса публикации"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE scheduled_posts SET status = ? WHERE post_id = ?
            ''', (status, post_id))
            await db.commit()
    
    async def get_statistics(self) -> Dict:
        """Получение статистики"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT COUNT(*) FROM users')
            total_users = (await cursor.fetchone())[0]
            
            cursor = await db.execute('''
                SELECT tariff, COUNT(*) as count FROM users GROUP BY tariff
            ''')
            tariff_stats = await cursor.fetchall()
            
            cursor = await db.execute('''
                SELECT SUM(amount) FROM payments WHERE status = 'completed'
            ''')
            total_revenue = (await cursor.fetchone())[0] or 0
            
            cursor = await db.execute('''
                SELECT COUNT(*) FROM scheduled_posts WHERE status = 'pending'
            ''')
            pending_posts = (await cursor.fetchone())[0]
            
            return {
                'total_users': total_users,
                'tariff_stats': dict(tariff_stats),
                'total_revenue': total_revenue,
                'pending_posts': pending_posts
            }
    
    async def get_all_users(self) -> List[Dict]:
        """Получение всех пользователей"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM users ORDER BY registered_at DESC')
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def update_tariff_price(self, tariff_name: str, price: int):
        """Обновление цены тарифа"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO tariff_prices (tariff_name, price)
                VALUES (?, ?)
            ''', (tariff_name, price))
            await db.commit()
    
    async def get_tariff_prices(self) -> Dict:
        """Получение цен тарифов"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM tariff_prices')
            rows = await cursor.fetchall()
            return {row['tariff_name']: row['price'] for row in rows}
    
    async def add_private_channel(self, tariff_name: str, channel_id: str, invite_link: str):
        """Добавление приватного канала для тарифа"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO private_channels (tariff_name, channel_id, invite_link)
                VALUES (?, ?, ?)
            ''', (tariff_name, channel_id, invite_link))
            await db.commit()
    
    async def get_private_channel(self, tariff_name: str) -> Optional[Dict]:
        """Получение приватного канала для тарифа"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                'SELECT * FROM private_channels WHERE tariff_name = ?', 
                (tariff_name,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def add_payment(self, user_id: int, tariff: str, amount: int, status: str = 'completed'):
        """Добавление информации о платеже"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO payments (user_id, tariff, amount, status)
                VALUES (?, ?, ?, ?)
            ''', (user_id, tariff, amount, status))
            await db.commit()

# ========== ТЕЛЕГРАМ БОТ ==========
class SchedulerBot:
    def __init__(self):
        self.application = None
        self.scheduler = AsyncIOScheduler()
        self.user_states = {}
        self.db = Database(DATABASE_PATH)
        
    async def setup(self):
        """Настройка бота"""
        # Инициализация базы данных
        await self.db.init_db()
        
        # Создание приложения
        self.application = Application.builder().token(BOT_TOKEN).build()
        
        # Настройка обработчиков
        self.setup_handlers()
        
        # Инициализация приложения
        await self.application.initialize()
        await self.application.start()
        
        # Запуск планировщика
        self.scheduler.start()
        
        # Запуск проверки подписок
        asyncio.create_task(self.check_subscriptions())
        
        logger.info("Bot setup completed")
        
    def setup_handlers(self):
        """Настройка обработчиков"""
        # Команда /start
        self.application.add_handler(CommandHandler("start", self.start))
        
        # Обработчики callback
        self.application.add_handler(CallbackQueryHandler(
            self.handle_callback, 
            pattern="^(schedule_post|my_channels|tariffs|help|admin_panel|back_to_menu|add_channel)$"
        ))
        
        self.application.add_handler(CallbackQueryHandler(
            self.handle_schedule_callback,
            pattern="^schedule_"
        ))
        
        self.application.add_handler(CallbackQueryHandler(
            self.handle_tariff_callback,
            pattern="^tariff_"
        ))
        
        self.application.add_handler(CallbackQueryHandler(
            self.handle_admin_callback,
            pattern="^admin_"
        ))
        
        self.application.add_handler(CallbackQueryHandler(
            self.handle_channel_selection,
            pattern="^select_channel_"
        ))
        
        # Обработчики сообщений
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.handle_message
        ))
        
        self.application.add_handler(MessageHandler(
            filters.PHOTO | filters.VIDEO,
            self.handle_message
        ))
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start"""
        user = update.effective_user
        await self.db.add_user(user.id, user.username, user.first_name, user.last_name)
        
        keyboard = [
            [InlineKeyboardButton("📅 Запланировать пост", callback_data="schedule_post")],
            [InlineKeyboardButton("📊 Мои каналы", callback_data="my_channels")],
            [InlineKeyboardButton("💎 Тарифы", callback_data="tariffs")],
            [InlineKeyboardButton("📋 Помощь", callback_data="help")]
        ]
        
        if user.id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("👑 Админ панель", callback_data="admin_panel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"Привет, {user.first_name}!\n\n"
            "Я бот для планирования публикаций в Telegram каналах.\n"
            "Выберите действие:",
            reply_markup=reply_markup
        )
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка callback запросов"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = query.from_user.id
        
        if data == "schedule_post":
            await self.show_schedule_options(query)
        elif data == "my_channels":
            await self.show_user_channels(query)
        elif data == "tariffs":
            await self.show_tariffs(query)
        elif data == "help":
            await self.show_help(query)
        elif data == "admin_panel":
            await self.show_admin_panel(query)
        elif data == "add_channel":
            await query.edit_message_text(
                "Отправьте мне ссылку на ваш канал в формате:\n"
                "https://t.me/channel_username\n\n"
                "Или перешлите любое сообщение из канала."
            )
            self.user_states[user_id] = {"action": "add_channel"}
        elif data == "back_to_menu":
            await self.show_main_menu(query)
    
    async def show_schedule_options(self, query):
        """Показать варианты планирования"""
        keyboard = [
            [InlineKeyboardButton("⏰ Через час", callback_data="schedule_1h")],
            [InlineKeyboardButton("🕐 Через 3 часа", callback_data="schedule_3h")],
            [InlineKeyboardButton("🕒 Через 6 часов", callback_data="schedule_6h")],
            [InlineKeyboardButton("📅 Выбрать своё время", callback_data="schedule_custom")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📅 Выберите время публикации:",
            reply_markup=reply_markup
        )
    
    async def handle_schedule_callback(self, query, data):
        """Обработка callback для планирования"""
        user_id = query.from_user.id
        
        if data == "schedule_1h":
            schedule_time = datetime.now() + timedelta(hours=1)
            await self.request_post_content(query, schedule_time)
        elif data == "schedule_3h":
            schedule_time = datetime.now() + timedelta(hours=3)
            await self.request_post_content(query, schedule_time)
        elif data == "schedule_6h":
            schedule_time = datetime.now() + timedelta(hours=6)
            await self.request_post_content(query, schedule_time)
        elif data == "schedule_custom":
            await query.edit_message_text(
                "Введите время публикации в формате:\n"
                "ГГГГ.ММ.ДД ЧЧ:ММ\n\n"
                "Например: 2025.12.31 15:30"
            )
            self.user_states[user_id] = {"action": "awaiting_custom_time"}
    
    async def request_post_content(self, query, schedule_time: datetime):
        """Запрос контента для публикации"""
        user_id = query.from_user.id
        self.user_states[user_id] = {
            "action": "awaiting_content",
            "schedule_time": schedule_time
        }
        
        await query.edit_message_text(
            f"⏰ Запланировано на: {schedule_time.strftime('%Y.%m.%d %H:%M')}\n\n"
            "Отправьте мне контент для публикации:\n"
            "• Текст\n"
            "• Фото с подписью\n"
            "• Видео с подписью\n\n"
            "После отправки контента выберите канал для публикации."
        )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений и медиа"""
        user_id = update.effective_user.id
        message = update.message
        
        if user_id not in self.user_states:
            return
        
        state = self.user_states[user_id]
        
        if state["action"] == "awaiting_content":
            await self.process_post_content(update, context, state)
        elif state["action"] == "awaiting_custom_time":
            await self.process_custom_time(update, context)
        elif state["action"] == "add_channel":
            await self.process_channel_addition(update, context)
    
    async def process_post_content(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: Dict):
        """Обработка контента для публикации"""
        user_id = update.effective_user.id
        message = update.message
        
        channels = await self.db.get_user_channels(user_id)
        if not channels:
            await message.reply_text(
                "У вас нет добавленных каналов.\n"
                "Сначала добавьте канал через меню 'Мои каналы'."
            )
            del self.user_states[user_id]
            return
        
        keyboard = []
        for channel in channels:
            keyboard.append([
                InlineKeyboardButton(
                    f"📢 {channel['channel_name']}",
                    callback_data=f"select_channel_{channel['channel_id']}"
                )
            ])
        keyboard.append([InlineKeyboardButton("◀️ Отмена", callback_data="back_to_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        context.user_data["post_content"] = {
            "text": message.caption or message.text,
            "media": None,
            "content_type": "text"
        }
        
        if message.photo:
            context.user_data["post_content"]["content_type"] = "photo"
            context.user_data["post_content"]["media"] = message.photo[-1].file_id
        elif message.video:
            context.user_data["post_content"]["content_type"] = "video"
            context.user_data["post_content"]["media"] = message.video.file_id
        
        context.user_data["schedule_time"] = state["schedule_time"]
        
        await message.reply_text(
            "Выберите канал для публикации:",
            reply_markup=reply_markup
        )
        
        del self.user_states[user_id]
    
    async def process_custom_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка пользовательского времени"""
        try:
            schedule_time = datetime.strptime(update.message.text, "%Y.%m.%d %H:%M")
            if schedule_time <= datetime.now():
                await update.message.reply_text("Время должно быть в будущем!")
                return
            
            user_id = update.effective_user.id
            self.user_states[user_id] = {
                "action": "awaiting_content",
                "schedule_time": schedule_time
            }
            
            await update.message.reply_text(
                f"⏰ Запланировано на: {schedule_time.strftime('%Y.%m.%d %H:%M')}\n\n"
                "Отправьте мне контент для публикации..."
            )
            
        except ValueError:
            await update.message.reply_text(
                "Неверный формат времени!\n"
                "Используйте: ГГГГ.ММ.ДД ЧЧ:ММ\n"
                "Пример: 2025.12.31 15:30"
            )
    
    async def process_channel_addition(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка добавления канала"""
        message = update.message
        
        if message.forward_from_chat and message.forward_from_chat.type in ["channel", "group"]:
            channel_id = str(message.forward_from_chat.id)
            channel_name = message.forward_from_chat.title
            
            success, msg = await self.db.add_channel(update.effective_user.id, channel_id, channel_name)
            await message.reply_text(msg)
        
        elif message.text and message.text.startswith("https://t.me/"):
            channel_username = message.text.split("/")[-1].replace("@", "")
            channel_id = f"@{channel_username}"
            
            success, msg = await self.db.add_channel(update.effective_user.id, channel_id, channel_username)
            await message.reply_text(msg)
        else:
            await message.reply_text(
                "Не удалось определить канал.\n"
                "Отправьте ссылку или перешлите сообщение из канала."
            )
        
        if update.effective_user.id in self.user_states:
            del self.user_states[update.effective_user.id]
    
    async def handle_channel_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбора канала"""
        query = update.callback_query
        await query.answer()
        
        if not query.data.startswith("select_channel_"):
            return
        
        channel_id = query.data.replace("select_channel_", "")
        user_id = query.from_user.id
        
        post_content = context.user_data.get("post_content")
        schedule_time = context.user_data.get("schedule_time")
        
        if not post_content or not schedule_time:
            await query.edit_message_text("Ошибка: данные не найдены")
            return
        
        post_id = await self.db.add_scheduled_post(
            user_id=user_id,
            channel_id=channel_id,
            content_type=post_content["content_type"],
            content=post_content["text"],
            media_path=post_content["media"],
            scheduled_time=schedule_time
        )
        
        await self.schedule_post(post_id, channel_id, post_content, schedule_time)
        
        await query.edit_message_text(
            f"✅ Пост запланирован!\n\n"
            f"📅 Время: {schedule_time.strftime('%Y.%m.%d %H:%M')}\n"
            f"📢 Канал: {channel_id}\n"
            f"📝 ID публикации: {post_id}"
        )
        
        if "post_content" in context.user_data:
            del context.user_data["post_content"]
        if "schedule_time" in context.user_data:
            del context.user_data["schedule_time"]
    
    async def schedule_post(self, post_id: int, channel_id: str, content: Dict, schedule_time: datetime):
        """Планирование публикации"""
        
        async def publish_post():
            try:
                bot = self.application.bot
                
                if content["content_type"] == "text":
                    await bot.send_message(
                        chat_id=channel_id,
                        text=content["text"],
                        parse_mode=ParseMode.HTML
                    )
                elif content["content_type"] == "photo":
                    await bot.send_photo(
                        chat_id=channel_id,
                        photo=content["media"],
                        caption=content.get("text"),
                        parse_mode=ParseMode.HTML
                    )
                elif content["content_type"] == "video":
                    await bot.send_video(
                        chat_id=channel_id,
                        video=content["media"],
                        caption=content.get("text"),
                        parse_mode=ParseMode.HTML
                    )
                
                await self.db.update_post_status(post_id, "published")
                logger.info(f"Post {post_id} published to {channel_id}")
                
            except Exception as e:
                logger.error(f"Failed to publish post {post_id}: {e}")
                await self.db.update_post_status(post_id, "failed")
        
        self.scheduler.add_job(
            publish_post,
            'date',
            run_date=schedule_time,
            id=f"post_{post_id}"
        )
    
    async def show_user_channels(self, query):
        """Показать каналы пользователя"""
        user_id = query.from_user.id
        channels = await self.db.get_user_channels(user_id)
        
        if not channels:
            text = "📭 У вас нет добавленных каналов"
            keyboard = [[InlineKeyboardButton("➕ Добавить канал", callback_data="add_channel")]]
        else:
            text = "📢 Ваши каналы:\n\n"
            for channel in channels:
                text += f"• {channel['channel_name']} ({channel['channel_id']})\n"
            
            keyboard = [
                [InlineKeyboardButton("➕ Добавить канал", callback_data="add_channel")],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    async def show_tariffs(self, query):
        """Показать тарифы"""
        user_id = query.from_user.id
        user = await self.db.get_user(user_id)
        tariff_prices = await self.db.get_tariff_prices()
        
        text = "💎 Доступные тарифы:\n\n"
        
        for tariff_name, tariff_data in TARIFFS.items():
            price = tariff_prices.get(tariff_name, tariff_data['price'])
            current = " (текущий)" if user and user['tariff'] == tariff_name else ""
            
            text += f"<b>{tariff_data['name']}{current}</b>\n"
            text += f"💰 Цена: {price} звезд\n"
            text += f"📢 Каналов: {tariff_data['channels_limit']}\n"
            text += f"📊 Постов в день: {tariff_data['posts_per_day']}\n"
            text += f"📅 Длительность: {tariff_data['duration_days']} дней\n"
            text += "\n"
        
        keyboard = []
        for tariff_name in TARIFFS.keys():
            price = tariff_prices.get(tariff_name, TARIFFS[tariff_name]['price'])
            keyboard.append([
                InlineKeyboardButton(
                    f"Купить {TARIFFS[tariff_name]['name']} - {price} звезд",
                    callback_data=f"tariff_{tariff_name}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    
    async def handle_tariff_callback(self, query, data):
        """Обработка покупки тарифа"""
        tariff_name = data.replace("tariff_", "")
        
        if tariff_name not in TARIFFS:
            await query.edit_message_text("Тариф не найден")
            return
        
        user_id = query.from_user.id
        tariff_prices = await self.db.get_tariff_prices()
        price = tariff_prices.get(tariff_name, TARIFFS[tariff_name]['price'])
        
        private_channel = await self.db.get_private_channel(tariff_name)
        
        if private_channel:
            await self.db.update_user_tariff(user_id, tariff_name)
            await self.db.add_payment(user_id, tariff_name, price)
            
            await query.edit_message_text(
                f"✅ Тариф успешно активирован!\n\n"
                f"💎 Тариф: {TARIFFS[tariff_name]['name']}\n"
                f"💰 Стоимость: {price} звезд\n\n"
                f"🔗 Ссылка на приватный канал:\n"
                f"{private_channel['invite_link']}\n\n"
                f"⚠️ Внимание: доступ к каналу будет отозван через 2 часа, "
                f"если вы не войдете самостоятельно."
            )
            
            await self.schedule_channel_kick(user_id, private_channel['channel_id'])
            
        else:
            await query.edit_message_text(
                "⚠️ Приватный канал для этого тарифа еще не настроен.\n"
                "Обратитесь к администратору."
            )
    
    async def schedule_channel_kick(self, user_id: int, channel_id: str):
        """Планирование удаления пользователя из канала"""
        
        async def kick_user():
            try:
                bot = self.application.bot
                await bot.ban_chat_member(channel_id, user_id)
                await bot.unban_chat_member(channel_id, user_id)
                logger.info(f"User {user_id} kicked from channel {channel_id}")
            except Exception as e:
                logger.error(f"Failed to kick user {user_id}: {e}")
        
        kick_time = datetime.now() + timedelta(hours=2)
        self.scheduler.add_job(
            kick_user,
            'date',
            run_date=kick_time,
            id=f"kick_{user_id}_{channel_id}"
        )
    
    async def show_admin_panel(self, query):
        """Показать админ панель"""
        if query.from_user.id != ADMIN_ID:
            await query.edit_message_text("Доступ запрещен")
            return
        
        stats = await self.db.get_statistics()
        
        text = f"""
👑 <b>Админ панель</b>

📊 <b>Статистика:</b>
👥 Пользователей: {stats['total_users']}
💰 Общая прибыль: {stats['total_revenue']} звезд
📅 Ожидающих публикаций: {stats['pending_posts']}

<b>Пользователи по тарифам:</b>
"""
        
        for tariff, count in stats['tariff_stats'].items():
            text += f"  {tariff}: {count}\n"
        
        keyboard = [
            [InlineKeyboardButton("📊 Полная статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("👥 Список пользователей", callback_data="admin_users")],
            [InlineKeyboardButton("💰 Изменить цены", callback_data="admin_prices")],
            [InlineKeyboardButton("🔗 Управление каналами", callback_data="admin_channels")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    
    async def handle_admin_callback(self, query, data):
        """Обработка админ действий"""
        if query.from_user.id != ADMIN_ID:
            await query.edit_message_text("Доступ запрещен")
            return
        
        if data == "admin_stats":
            await self.show_full_stats(query)
        elif data == "admin_users":
            await self.export_users(query)
        elif data == "admin_prices":
            await self.show_price_management(query)
        elif data == "admin_channels":
            await self.show_channel_management(query)
    
    async def show_full_stats(self, query):
        """Показать полную статистику"""
        stats = await self.db.get_statistics()
        users = await self.db.get_all_users()
        
        text = f"""
📈 <b>Полная статистика</b>

👥 <b>Всего пользователей:</b> {stats['total_users']}
💰 <b>Общая прибыль:</b> {stats['total_revenue']} звезд
📅 <b>Ожидающих публикаций:</b> {stats['pending_posts']}

<b>Распределение по тарифам:</b>
"""
        
        for tariff, count in stats['tariff_stats'].items():
            percentage = (count / stats['total_users'] * 100) if stats['total_users'] > 0 else 0
            text += f"  {tariff}: {count} ({percentage:.1f}%)\n"
        
        text += f"\n<b>Последние 5 регистраций:</b>\n"
        for user in users[:5]:
            reg_date = datetime.fromisoformat(user['registered_at']).strftime('%Y.%m.%d')
            text += f"  {user['user_id']} - {user['first_name']} ({reg_date})\n"
        
        keyboard = [[InlineKeyboardButton("◀️ Назад в админку", callback_data="admin_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    
    async def export_users(self, query):
        """Экспорт пользователей"""
        users = await self.db.get_all_users()
        
        if not users:
            await query.edit_message_text("Нет пользователей для экспорта")
            return
        
        export_text = "ID,Username,First Name,Last Name,Tariff,Registered\n"
        for user in users:
            export_text += f"{user['user_id']},"
            export_text += f"{user['username'] or ''},"
            export_text += f"{user['first_name']},"
            export_text += f"{user['last_name'] or ''},"
            export_text += f"{user['tariff']},"
            export_text += f"{user['registered_at']}\n"
        
        await query.edit_message_text("Файл с пользователями готов!")
        await query.message.reply_document(
            document=export_text.encode('utf-8'),
            filename="users_export.csv",
            caption="📋 Экспорт пользователей"
        )
        
        keyboard = [[InlineKeyboardButton("◀️ Назад в админку", callback_data="admin_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("Выберите действие:", reply_markup=reply_markup)
    
    async def show_price_management(self, query):
        """Управление ценами тарифов"""
        await query.edit_message_text(
            "Функция изменения цен временно недоступна.\n"
            "Для изменения цен отредактируйте переменную TARIFFS в коде."
        )
    
    async def show_channel_management(self, query):
        """Управление приватными каналами"""
        await query.edit_message_text(
            "Функция управления каналами временно недоступна.\n"
            "Для настройки приватных каналов обратитесь к разработчику."
        )
    
    async def show_help(self, query):
        """Показать справку"""
        text = """
🤖 <b>Помощь по боту</b>

<b>Основные функции:</b>
1. <b>Запланировать пост</b> - создание отложенной публикации
2. <b>Мои каналы</b> - управление подключенными каналами
3. <b>Тарифы</b> - покупка подписки на расширенные возможности

<b>Формат времени:</b>
При выборе своего времени используйте формат:
<b>ГГГГ.ММ.ДД ЧЧ:ММ</b>
Пример: <code>2025.12.31 15:30</code>
"""
        
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    
    async def show_main_menu(self, query):
        """Показать главное меню"""
        keyboard = [
            [InlineKeyboardButton("📅 Запланировать пост", callback_data="schedule_post")],
            [InlineKeyboardButton("📊 Мои каналы", callback_data="my_channels")],
            [InlineKeyboardButton("💎 Тарифы", callback_data="tariffs")],
            [InlineKeyboardButton("📋 Помощь", callback_data="help")]
        ]
        
        if query.from_user.id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("👑 Админ панель", callback_data="admin_panel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Главное меню. Выберите действие:",
            reply_markup=reply_markup
        )
    
    async def check_subscriptions(self):
        """Проверка и обновление подписок"""
        while True:
            try:
                async with aiosqlite.connect(DATABASE_PATH) as conn:
                    cursor = await conn.execute('''
                        SELECT user_id FROM users 
                        WHERE subscription_end < datetime('now') 
                        AND tariff != 'free'
                    ''')
                    expired_users = await cursor.fetchall()
                    
                    for (user_id,) in expired_users:
                        await conn.execute('''
                            UPDATE users SET tariff = 'free' WHERE user_id = ?
                        ''', (user_id,))
                        
                        try:
                            await self.application.bot.send_message(
                                user_id,
                                "⚠️ Ваша подписка истекла!\n\n"
                                "Для продолжения использования премиум функций "
                                "продлите подписку в разделе 'Тарифы'."
                            )
                        except:
                            pass
                    
                    await conn.commit()
            
            except Exception as e:
                logger.error(f"Error checking subscriptions: {e}")
            
            await asyncio.sleep(3600)

# ========== ВЕБ-СЕРВЕР ДЛЯ WEBHOOK ==========
bot_instance = SchedulerBot()

async def handle_webhook(request):
    """Обработчик webhook"""
    try:
        data = await request.json()
        update = Update.de_json(data, bot_instance.application.bot)
        await bot_instance.application.process_update(update)
        return web.Response()
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.Response(status=500)

async def health_check(request):
    """Проверка здоровья"""
    return web.Response(text="Bot is running!")

async def setup_webhook():
    """Настройка webhook"""
    domain = os.getenv('RAILWAY_PUBLIC_DOMAIN')
    
    if domain:
        webhook_url = f"https://{domain}/webhook"
        try:
            await bot_instance.application.bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=True
            )
            logger.info(f"Webhook set to: {webhook_url}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
    else:
        logger.info("Running in polling mode (local development)")

async def main():
    """Основная функция запуска"""
    # Инициализируем бота
    await bot_instance.setup()
    
    # Настраиваем webhook если на Railway
    await setup_webhook()
    
    # Создаем веб-сервер для обработки webhook
    app = web.Application()
    app.router.add_post('/webhook', handle_webhook)
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    # Запускаем сервер
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    logger.info(f"Server started on port {PORT}")
    
    # Бесконечный цикл
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
