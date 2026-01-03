import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = "8569312600:AAGiuvWLi2n84SYahF_pyye94xFqKgNl2IU"  # Ваш новый токен
ADMIN_ID = 6646433980

# Хранилище для состояния
user_states = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    user = update.effective_user
    logger.info(f"User {user.id} started the bot")
    
    # Простое меню
    menu_text = f"""
🎉 *Бот запущен!*

👋 Привет, {user.first_name}!
🆔 Ваш ID: `{user.id}`

📋 *Доступные команды:*
/start - Начать работу
/help - Помощь
/schedule - Запланировать пост
/channels - Мои каналы
/tariffs - Тарифы

⚡ *Бот готов к работе!*
"""
    
    await update.message.reply_text(menu_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /help"""
    help_text = """
🤖 *Помощь по боту*

*Основные функции:*
1. 📅 *Планирование постов* - Отправьте /schedule
2. 📢 *Управление каналами* - Отправьте /channels  
3. 💎 *Тарифная система* - Отправьте /tariffs

*Формат времени:* ГГГГ.ММ.ДД ЧЧ:ММ
*Пример:* 2025.12.31 15:30

Для начала работы отправьте /start
"""
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать планирование"""
    user_id = update.effective_user.id
    user_states[user_id] = "waiting_for_time"
    
    await update.message.reply_text(
        "📅 *Планирование поста*\n\n"
        "Отправьте время публикации в формате:\n"
        "`ГГГГ.ММ.ДД ЧЧ:ММ`\n\n"
        "*Пример:* 2025.12.31 15:30\n"
        "Или выберите:\n"
        "• `now` - сейчас\n"
        "• `1h` - через час\n"
        "• `3h` - через 3 часа",
        parse_mode="Markdown"
    )

async def channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Мои каналы"""
    await update.message.reply_text(
        "📢 *Управление каналами*\n\n"
        "Чтобы добавить канал:\n"
        "1. Перешлите любое сообщение из канала\n"
        "2. Или отправьте ссылку на канал\n\n"
        "Мои каналы будут отображаться здесь.",
        parse_mode="Markdown"
    )

async def tariffs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тарифы"""
    tariffs_text = """
💎 *Доступные тарифы:*

*1. Базовый* - 299 звёзд
• 2 канала
• 5 постов в день
• 30 дней

*2. Премиум* - 599 звёзд  
• 5 каналов
• 20 постов в день
• 30 дней

*3. VIP* - 999 звёзд
• 10 каналов
• 50 постов в день
• 30 дней

Для покупки тарифа свяжитесь с администратором.
"""
    await update.message.reply_text(tariffs_text, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id in user_states:
        state = user_states[user_id]
        
        if state == "waiting_for_time":
            # Обработка времени
            await update.message.reply_text(
                f"⏰ Время получено: {text}\n"
                f"Теперь отправьте контент для публикации (текст, фото или видео)."
            )
            user_states[user_id] = "waiting_for_content"
        elif state == "waiting_for_content":
            # Обработка контента
            await update.message.reply_text(
                f"✅ Контент получен!\n"
                f"Пост запланирован.\n\n"
                f"Используйте /channels для управления каналами."
            )
            del user_states[user_id]
    else:
        # Эхо-ответ
        await update.message.reply_text(
            f"📝 Вы написали: {text}\n\n"
            f"Используйте /help для просмотра команд."
        )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото"""
    user_id = update.effective_user.id
    
    if user_id in user_states and user_states[user_id] == "waiting_for_content":
        await update.message.reply_text(
            "✅ Фото получено! Пост запланирован.\n"
            "Используйте /channels для управления каналами."
        )
        del user_states[user_id]
    else:
        await update.message.reply_text(
            "📸 Фото получено!\n"
            "Для планирования поста с фото используйте /schedule"
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ошибок"""
    logger.error(f"Update {update} caused error {context.error}")
    
    if "Conflict" in str(context.error):
        logger.error("КОНФЛИКТ! Запущено несколько экземпляров бота!")
        logger.error("Остановите все другие инстансы бота с этим токеном!")
        
        try:
            await update.message.reply_text(
                "⚠️ *Обнаружен конфликт!*\n\n"
                "Запущено несколько экземпляров бота.\n"
                "Пожалуйста, подождите 30 секунд и попробуйте снова.\n"
                "Администратор уже устраняет проблему.",
                parse_mode="Markdown"
            )
        except:
            pass

def main():
    """Запуск бота"""
    print("=" * 50)
    print("🚀 ЗАПУСК ТЕЛЕГРАМ БОТА")
    print("=" * 50)
    print(f"Токен: {BOT_TOKEN[:10]}...")
    print(f"Админ ID: {ADMIN_ID}")
    print("=" * 50)
    
    try:
        # Создаем приложение
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Добавляем обработчики команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("schedule", schedule))
        application.add_handler(CommandHandler("channels", channels))
        application.add_handler(CommandHandler("tariffs", tariffs))
        
        # Добавляем обработчики сообщений
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        
        # Добавляем обработчик ошибок
        application.add_error_handler(error_handler)
        
        # Запускаем бота
        print("✅ Бот инициализирован")
        print("⏳ Запускаю polling...")
        
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
            poll_interval=0.5,
            timeout=10
        )
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
