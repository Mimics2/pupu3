import os
import logging
import asyncio
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN', '8569312600:AAGiuvWLi2n84SYahF_pyye94xFqKgNl2IU')
ADMIN_ID = int(os.getenv('ADMIN_ID', '6646433980'))
PORT = int(os.getenv('PORT', '8000'))

class TelegramBot:
    def __init__(self):
        self.application = None
        self.webhook_url = None
        
    async def setup(self):
        """Настройка бота"""
        logger.info("🚀 Инициализация бота...")
        logger.info(f"Токен: {BOT_TOKEN[:10]}...")
        logger.info(f"Порт: {PORT}")
        
        # Создаем приложение
        self.application = Application.builder().token(BOT_TOKEN).build()
        
        # Добавляем обработчики
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help))
        self.application.add_handler(CommandHandler("ping", self.ping))
        self.application.add_handler(CommandHandler("status", self.status))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.echo))
        
        # Инициализируем
        await self.application.initialize()
        await self.application.start()
        
        logger.info("✅ Бот инициализирован")
        
        # Настраиваем webhook
        await self.setup_webhook()
        
    async def setup_webhook(self):
        """Настройка webhook"""
        # Проверяем все возможные переменные для домена
        domain = None
        
        # 1. RAILWAY_PUBLIC_DOMAIN (основная)
        if os.getenv('RAILWAY_PUBLIC_DOMAIN'):
            domain = os.getenv('RAILWAY_PUBLIC_DOMAIN')
            logger.info(f"✅ Использую RAILWAY_PUBLIC_DOMAIN: {domain}")
        
        # 2. Проверяем другие переменные Railway
        elif os.getenv('RAILWAY_STATIC_URL'):
            domain = os.getenv('RAILWAY_STATIC_URL').replace('https://', '').replace('http://', '')
            logger.info(f"✅ Использую RAILWAY_STATIC_URL: {domain}")
            
        elif os.getenv('RAILWAY_ENVIRONMENT_NAME'):
            project_name = os.getenv('RAILWAY_PROJECT_NAME', 'telegram-bot')
            domain = f"{project_name}.up.railway.app"
            logger.info(f"✅ Генерирую домен: {domain}")
        
        if domain:
            self.webhook_url = f"https://{domain}/webhook"
            
            # Удаляем старый webhook
            await self.application.bot.delete_webhook(drop_pending_updates=True)
            logger.info("🗑️ Старый webhook удален")
            
            # Устанавливаем новый webhook
            await self.application.bot.set_webhook(
                url=self.webhook_url,
                drop_pending_updates=True,
                max_connections=40,
                allowed_updates=['message', 'callback_query']
            )
            
            logger.info(f"✅ Webhook установлен: {self.webhook_url}")
            
            # Проверяем webhook
            webhook_info = await self.application.bot.get_webhook_info()
            logger.info(f"📊 Webhook информация:")
            logger.info(f"   URL: {webhook_info.url}")
            logger.info(f"   Ожидающих обновлений: {webhook_info.pending_update_count}")
            
            if webhook_info.url == self.webhook_url:
                logger.info("✅ Webhook успешно настроен!")
            else:
                logger.error(f"❌ Webhook не настроен правильно!")
                logger.error(f"   Ожидалось: {self.webhook_url}")
                logger.error(f"   Получено: {webhook_info.url}")
        else:
            logger.warning("⚠️ Домен не найден. Запускаю в режиме polling...")
            await self.application.updater.start_polling()
            
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start"""
        user = update.effective_user
        logger.info(f"👤 Пользователь {user.id} вызвал /start")
        
        keyboard = [
            [InlineKeyboardButton("✅ Тест кнопок", callback_data="test")],
            [InlineKeyboardButton("🔄 Проверить статус", callback_data="status")],
            [InlineKeyboardButton("📋 Команды", callback_data="commands")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🎉 **Бот запущен и работает!**\n\n"
            f"👋 Привет, {user.first_name}!\n"
            f"🆔 Ваш ID: `{user.id}`\n"
            f"🌐 Режим: {'Webhook' if self.webhook_url else 'Polling'}\n\n"
            f"Выберите действие:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /help"""
        await update.message.reply_text(
            "🤖 **Помощь по боту**\n\n"
            "📋 **Основные команды:**\n"
            "• /start - Начать работу с ботом\n"
            "• /help - Показать эту справку\n"
            "• /ping - Проверить отклик бота\n"
            "• /status - Статус бота\n\n"
            "🎯 **Функции бота:**\n"
            "• 📅 Планирование публикаций\n"
            "• 📢 Управление каналами\n"
            "• 💎 Тарифная система\n"
            "• 👑 Админ-панель\n\n"
            "⏰ **Формат времени:** ГГГГ.ММ.ДД ЧЧ:ММ",
            parse_mode="Markdown"
        )
        
    async def ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Проверка работы бота"""
        await update.message.reply_text("🏓 **Понг!** Бот активен и отвечает!")
        
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статус бота"""
        mode = "🌐 **Webhook**" if self.webhook_url else "🔄 **Polling**"
        domain = self.webhook_url if self.webhook_url else "Не настроен"
        
        await update.message.reply_text(
            f"📊 **Статус бота**\n\n"
            f"{mode}\n"
            f"🔗 Webhook: `{domain}`\n"
            f"✅ Состояние: Работает нормально\n"
            f"🕐 Время: {update.message.date.strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode="Markdown"
        )
        
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий кнопок"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "test":
            await query.edit_message_text("✅ **Тест пройден!**\nКнопки работают корректно!")
        elif query.data == "status":
            mode = "Webhook" if self.webhook_url else "Polling"
            await query.edit_message_text(f"🟢 **Статус:** Бот активен\n**Режим:** {mode}")
        elif query.data == "commands":
            await query.edit_message_text("📋 **Доступные команды:**\n/start\n/help\n/ping\n/status")
            
    async def echo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Эхо-ответ"""
        text = update.message.text
        logger.info(f"📨 Сообщение от {update.effective_user.id}: {text}")
        await update.message.reply_text(f"📝 Вы написали: {text}")

# Создаем экземпляр бота
bot = TelegramBot()

async def handle_webhook(request):
    """Обработчик webhook"""
    try:
        data = await request.json()
        update = Update.de_json(data, bot.application.bot)
        await bot.application.process_update(update)
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"❌ Ошибка в webhook: {e}")
        return web.Response(status=500, text=str(e))

async def health_check(request):
    """Проверка здоровья"""
    return web.Response(text="🤖 Telegram Bot is running on Railway!")

async def webhook_info(request):
    """Информация о webhook"""
    try:
        webhook_info = await bot.application.bot.get_webhook_info()
        return web.json_response({
            "status": "online",
            "webhook_url": webhook_info.url,
            "pending_updates": webhook_info.pending_update_count,
            "has_custom_certificate": webhook_info.has_custom_certificate,
            "bot_username": (await bot.application.bot.get_me()).username
        })
    except:
        return web.json_response({"status": "bot_not_initialized"})

async def main():
    """Основная функция запуска"""
    logger.info("🚀 Запуск Telegram бота...")
    
    # Инициализируем бота
    await bot.setup()
    
    # Создаем веб-сервер
    app = web.Application()
    
    # Добавляем маршруты
    app.router.add_post('/webhook', handle_webhook)
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    app.router.add_get('/webhook-info', webhook_info)
    
    # Запускаем сервер
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    logger.info(f"✅ Сервер запущен на порту {PORT}")
    logger.info("⏳ Ожидаю обновления...")
    
    # Выводим информацию для отладки
    print("\n" + "="*50)
    print("🤖 TELEGRAM BOT READY")
    print("="*50)
    print(f"Bot Token: {BOT_TOKEN[:10]}...")
    print(f"Admin ID: {ADMIN_ID}")
    print(f"Port: {PORT}")
    print(f"Webhook URL: {bot.webhook_url or 'Not set'}")
    print("="*50)
    print("\nДля проверки:")
    print(f"1. Откройте: https://ваш-домен.railway.app/health")
    print(f"2. Напишите боту: /start")
    print("="*50 + "\n")
    
    # Бесконечный цикл
    await asyncio.Future()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
