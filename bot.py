import asyncio
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage

# ============================================================================
# ИНИЦИАЛИЗАЦИЯ И КОНФИГУРАЦИЯ
# ============================================================================

# Загружаем переменные окружения из .env файла
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Проверяем наличие токена
if not BOT_TOKEN or BOT_TOKEN == 'your_bot_token_from_botfather_here':
    print("\n❌ ОШИБКА: BOT_TOKEN не найден или не установлен!")
    print("📝 Инструкция:")
    print("  1. Откройте файл .env")
    print("  2. Замените 'your_bot_token_from_botfather_here' на реальный токен от @BotFather")
    print("  3. Сохраните файл")
    print("  4. Перезагрузите скрипт\n")
    exit(1)

# Инициализируем бота и диспетчер
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Временная зона для Минска
MINSK_TZ = ZoneInfo('Europe/Minsk')

# Хранилище напоминаний пользователей
# Структура: {user_id: {'enabled': bool, 'task': asyncio.Task or None}}
user_reminders = {}

# Константы для настройки
REMINDER_INTERVAL = 90  # минуты между напоминаниями (для 70 кг человека)
QUIET_START = 21        # начало "тихих часов" (21:00 = 9 PM)
QUIET_END = 9           # конец "тихих часов" (09:00 = 9 AM)

# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def create_keyboard():
    """Создает клавиатуру с кнопками управления напоминаниями"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🚰 Enable reminders"),
                KeyboardButton(text="⏸ Disable reminders")
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard


def is_quiet_hours() -> bool:
    """
    Проверяет, находится ли текущее время в 'тихих часах' (21:00 - 09:00 Minsk TZ)
    Возвращает True если сейчас 'тихие часы', False если нужно отправлять напоминания
    """
    now = datetime.now(MINSK_TZ)
    current_hour = now.hour
    
    # Если сейчас между 21:00 и 09:00 - тихие часы
    is_quiet = current_hour >= QUIET_START or current_hour < QUIET_END
    
    return is_quiet


def get_next_reminder_time() -> datetime:
    """
    Вычисляет время следующего напоминания с учетом тихих часов
    Если сейчас тихие часы - вернет время на 09:00, иначе время через REMINDER_INTERVAL минут
    """
    now = datetime.now(MINSK_TZ)
    
    if is_quiet_hours():
        # Если в тихих часах, следующее напоминание в 09:00
        if now.hour >= QUIET_START:
            # Сейчас вечер/ночь (21:00+), ждем до 09:00 завтра
            next_reminder = now.replace(hour=QUIET_END, minute=0, second=0, microsecond=0)
            next_reminder += timedelta(days=1)
        else:
            # Сейчас утро (до 09:00), ждем до 09:00 сегодня
            next_reminder = now.replace(hour=QUIET_END, minute=0, second=0, microsecond=0)
    else:
        # Не в тихих часах, следующее напоминание через REMINDER_INTERVAL минут
        next_reminder = now + timedelta(minutes=REMINDER_INTERVAL)
    
    return next_reminder


# ============================================================================
# ОСНОВНЫЕ ФУНКЦИИ ОТПРАВКИ И УПРАВЛЕНИЯ НАПОМИНАНИЯМИ
# ============================================================================

async def send_reminder(user_id: int):
    """Отправляет напоминание пользователю"""
    if is_quiet_hours():
        # Не отправляем в тихие часы
        return
    
    try:
        await bot.send_message(
            user_id,
            "💧 Time to drink water! Stay hydrated! 💧",
            reply_markup=create_keyboard()
        )
        print(f"✅ Напоминание отправлено пользователю {user_id}")
    except Exception as e:
        print(f"⚠️ Ошибка при отправке напоминания пользователю {user_id}: {e}")


async def reminder_loop(user_id: int):
    """
    Бесконечный цикл отправки напоминаний для пользователя
    Автоматически пропускает тихие часы (21:00 - 09:00)
    """
    print(f"🔄 Цикл напоминаний запущен для пользователя {user_id}")
    
    while user_reminders.get(user_id, {}).get('enabled', False):
        try:
            # Получаем время следующего напоминания
            next_reminder_time = get_next_reminder_time()
            now = datetime.now(MINSK_TZ)
            sleep_seconds = (next_reminder_time - now).total_seconds()
            
            print(f"⏳ Пользователь {user_id}: ждем {sleep_seconds:.0f} сек до {next_reminder_time.strftime('%H:%M:%S')}")
            
            # Ждем до следующего напоминания
            await asyncio.sleep(max(1, sleep_seconds))  # min 1 сек чтобы не было бага
            
            # Проверяем еще раз, включены ли напоминания (могли отключить за время ожидания)
            if not user_reminders.get(user_id, {}).get('enabled', False):
                print(f"⏸ Пользователь {user_id} отключил напоминания во время ожидания")
                break
            
            # Отправляем напоминание
            await send_reminder(user_id)
            
        except asyncio.CancelledError:
            print(f"❌ Цикл напоминаний отменен для пользователя {user_id}")
            break
        except Exception as e:
            print(f"❌ Ошибка в цикле напоминаний пользователя {user_id}: {e}")
            await asyncio.sleep(5)  # Небольшая пауза перед повтором при ошибке
    
    # Очистка
    print(f"🛑 Цикл напоминаний остановлен для пользователя {user_id}")
    if user_id in user_reminders:
        user_reminders[user_id]['task'] = None


async def enable_reminders(user_id: int):
    """Включает напоминания для пользователя"""
    if user_id not in user_reminders:
        user_reminders[user_id] = {'enabled': False, 'task': None}
    
    # Если напоминания уже включены, ничего не делаем
    if user_reminders[user_id]['enabled']:
        return
    
    # Включаем напоминания и запускаем цикл
    user_reminders[user_id]['enabled'] = True
    task = asyncio.create_task(reminder_loop(user_id))
    user_reminders[user_id]['task'] = task
    print(f"✅ Напоминания включены для пользователя {user_id}")


async def disable_reminders(user_id: int):
    """Отключает напоминания для пользователя"""
    if user_id not in user_reminders:
        return
    
    # Отключаем флаг
    user_reminders[user_id]['enabled'] = False
    
    # Отменяем задачу если она есть
    if user_reminders[user_id]['task'] and not user_reminders[user_id]['task'].done():
        user_reminders[user_id]['task'].cancel()
        try:
            await user_reminders[user_id]['task']
        except asyncio.CancelledError:
            pass
    
    user_reminders[user_id]['task'] = None
    print(f"⏸ Напоминания отключены для пользователя {user_id}")


# ============================================================================
# ОБРАБОТЧИКИ СООБЩЕНИЙ
# ============================================================================

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    
    # Инициализируем пользователя если его еще нет
    if user_id not in user_reminders:
        user_reminders[user_id] = {'enabled': False, 'task': None}
    
    text = """

This bot helps you stay hydrated by sending you reminders to drink water every 90 minutes.

**Features:**
✅ Reminder interval: 90 minutes 
✅ Daily target: ~2.1-2.5 liters of water
✅ Quiet hours: 9 PM - 9 AM (Minsk time) - no notifications
✅ One-click enable/disable
"""
    
    await message.answer(text, reply_markup=create_keyboard())
    print(f"👤 Новый пользователь: {user_id} ({message.from_user.first_name})")


@dp.message(F.text == "Enable reminders")
async def enable_handler(message: types.Message):
    """Обработчик кнопки 'Включить напоминания'"""
    user_id = message.from_user.id
    
    await enable_reminders(user_id)
    
    await message.answer(
        "✅ Reminders enabled!\n\n"
        "💧 You will receive water reminders every 90 minutes (9 AM - 9 PM).\n"
        "🌙 Reminders will automatically stop at 9 PM and resume at 9 AM.\n\n"
        "Click '⏸ Disable reminders' to stop notifications.",
        reply_markup=create_keyboard()
    )


@dp.message(F.text == "Disable reminders")
async def disable_handler(message: types.Message):
    """Обработчик кнопки 'Отключить напоминания'"""
    user_id = message.from_user.id
    
    await disable_reminders(user_id)
    
    await message.answer(
        "Reminders disabled.\n\n"
        "Click 'Enable reminders' to receive notifications again.",
        reply_markup=create_keyboard()
    )


@dp.message()
async def echo_handler(message: types.Message):
    """Обработчик всех остальных сообщений"""
    await message.answer(
        "I understand only the buttons below. Please use them to control reminders.",
        reply_markup=create_keyboard()
    )


# ============================================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================================

async def main():
    """Главная функция - запуск бота"""
    print("\n" + "="*60)
    print("🤖 WATER REMINDER BOT STARTING")
    print("="*60)
    print(f"⏱  Reminder interval: {REMINDER_INTERVAL} minutes")
    print(f"🌙 Quiet hours: {QUIET_START}:00 PM - {QUIET_END}:00 AM (Minsk time)")
    print(f"📍 Timezone: Europe/Minsk")
    print("="*60)
    print("✅ Bot is running. Press Ctrl+C to stop.\n")
    
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        print("\n\n⛔ Bot stopped by user.")
    finally:
        await bot.session.close()
        print("✅ Bot session closed.\n")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n✅ Shutdown complete.")