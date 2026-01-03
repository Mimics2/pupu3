import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode
import asyncio

# Настройка логгирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = "8569312600:AAGiuvWLi2n84SYahF_pyye94xFqKgNl2IU"
ADMIN_ID = 6646433980

# Инициализация
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Хранилище
user_states = {}

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Обработка команды /start"""
    user = message.from_user
    logger.info(f"User {user.id} started the bot")
    
    menu_text = f"""
<b>🎉 БОТ ЗАПУЩЕН!</b>

👋 Привет, {user.first_name}!
🆔 Ваш ID: <code>{user.id}</code>

📋 <b>Доступные команды:</b>
/start - Начать работу
/help - Помощь
/schedule - Запланировать пост
/channels - Мои каналы
/tariffs - Тарифы
/status - Статус бота

⚡ <b>Бот готов к работе!</b>
"""
    
    await message.answer(menu_text)

@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Обработка команды /help"""
    help_text = """
<b>🤖 ПОМОЩЬ ПО БОТУ</b>

<b>ОСНОВНЫЕ ФУНКЦИИ:</b>
1. 📅 <b>Планирование постов</b> - Отправьте /schedule
2. 📢 <b>Управление каналами</b> - Отправьте /channels  
3. 💎 <b>Тарифная система</b> - Отправьте /tariffs

<b>Формат времени:</b> ГГГГ.ММ.ДД ЧЧ:ММ
<b>Пример:</b> 2025.12.31 15:30

Для начала работы отправьте /start
"""
    await message.answer(help_text)

@dp.message(Command("schedule"))
async def cmd_schedule(message: Message):
    """Начать планирование"""
    user_id = message.from_user.id
    user_states[user_id] = "waiting_for_time"
    
    await message.answer(
        "<b>📅 ПЛАНИРОВАНИЕ ПОСТА</b>\n\n"
        "Отправьте время публикации в формате:\n"
        "<code>ГГГГ.ММ.ДД ЧЧ:ММ</code>\n\n"
        "<b>Пример:</b> 2025.12.31 15:30\n"
        "Или выберите:\n"
        "• <code>now</code> - сейчас\n"
        "• <code>1h</code> - через час\n"
        "• <code>3h</code> - через 3 часа"
    )

@dp.message(Command("channels"))
async def cmd_channels(message: Message):
    """Мои каналы"""
    await message.answer(
        "<b>📢 УПРАВЛЕНИЕ КАНАЛАМИ</b>\n\n"
        "Чтобы добавить канал:\n"
        "1. Перешлите любое сообщение из канала\n"
        "2. Или отправьте ссылку на канал\n\n"
        "Мои каналы будут отображаться здесь."
    )

@dp.message(Command("tariffs"))
async def cmd_tariffs(message: Message):
    """Тарифы"""
    tariffs_text = """
<b>💎 ДОСТУПНЫЕ ТАРИФЫ:</b>

<b>1. БАЗОВЫЙ</b> - 299 звёзд
• 2 канала
• 5 постов в день
• 30 дней

<b>2. ПРЕМИУМ</b> - 599 звёзд  
• 5 каналов
• 20 постов в день
• 30 дней

<b>3. VIP</b> - 999 звёзд
• 10 каналов
• 50 постов в день
• 30 дней

Для покупки тарифа свяжитесь с администратором.
"""
    await message.answer(tariffs_text)

@dp.message(Command("status"))
async def cmd_status(message: Message):
    """Статус бота"""
    await message.answer(
        "<b>✅ БОТ РАБОТАЕТ НОРМАЛЬНО</b>\n\n"
        "Платформа: Railway\n"
        "Режим: Polling\n"
        "Статус: Активен\n\n"
        "Все функции доступны!"
    )

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    """Админ панель"""
    if message.from_user.id == ADMIN_ID:
        await message.answer(
            "<b>👑 АДМИН ПАНЕЛЬ</b>\n\n"
            "<b>Статистика:</b>\n"
            "• Пользователей: 1\n"
            "• Прибыль: 0 звёзд\n"
            "• Каналов: 0\n\n"
            "Команды админа будут здесь."
        )
    else:
        await message.answer("❌ Доступ запрещен")

@dp.message()
async def handle_all_messages(message: Message):
    """Обработка всех сообщений"""
    user_id = message.from_user.id
    text = message.text or ""
    
    if user_id in user_states:
        state = user_states[user_id]
        
        if state == "waiting_for_time":
            await message.answer(f"⏰ Время получено: {text}\nТеперь отправьте контент.")
            user_states[user_id] = "waiting_for_content"
        elif state == "waiting_for_content":
            await message.answer(f"✅ Контент получен!\nПост запланирован.")
            del user_states[user_id]
    elif text:
        await message.answer(f"📝 Вы написали: {text}\n\nИспользуйте /help для команд.")

async def main():
    """Основная функция"""
    print("=" * 50)
    print("🚀 ЗАПУСК ТЕЛЕГРАМ БОТА (aiogram)")
    print("=" * 50)
    print(f"Токен: {BOT_TOKEN[:10]}...")
    print(f"Админ ID: {ADMIN_ID}")
    print("=" * 50)
    
    try:
        # Запускаем polling
        print("✅ Бот запущен")
        await dp.start_polling(bot)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        await bot.session.close()

if __name__ == '__main__':
    asyncio.run(main())
