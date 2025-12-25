import asyncio
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage

# =====================================================================
# ИНИЦИАЛИЗАЦИЯ И КОНФИГУРАЦИЯ
# =====================================================================

# Загружаем переменные окружения из .env файла
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Проверяем наличие токена
if not BOT_TOKEN or BOT_TOKEN == "your_bot_token_from_botfather_here":
    print("\nERROR: BOT_TOKEN is not set or invalid.")
    print("Instructions:")
    print("  1. Open .env file")
    print("  2. Replace 'your_bot_token_from_botfather_here' with real token from @BotFather")
    print("  3. Save file")
    print("  4. Restart script\n")
    exit(1)

# Инициализируем бота и диспетчер
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Временная зона для Минска
MINSK_TZ = ZoneInfo("Europe/Minsk")

# Хранилище напоминаний пользователей
# {user_id: {"enabled": bool, "task": asyncio.Task | None}}
user_reminders: dict[int, dict] = {}

# Константы для настройки
REMINDER_INTERVAL = 90  # минуты между напоминаниями
QUIET_START = 21        # начало тихих часов (21:00)
QUIET_END = 9           # конец тихих часов (09:00)

# =====================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =====================================================================


def create_keyboard() -> ReplyKeyboardMarkup:
    """Создает клавиатуру с кнопками управления напоминаниями."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Enable reminders"),
                KeyboardButton(text="Disable reminders"),
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )
    return keyboard


def is_quiet_hours() -> bool:
    """
    Проверяет, находится ли текущее время в тихих часах (21:00–09:00).
    Возвращает True, если сейчас тихие часы.
    """
    now = datetime.now(MINSK_TZ)
    current_hour = now.hour
    return current_hour >= QUIET_START or current_hour < QUIET_END


def get_next_reminder_time() -> datetime:
    """
    Вычисляет время следующего напоминания с учетом тихих часов.
    Если сейчас тихие часы — возвращает ближайшее 09:00.
    Иначе — текущее время + REMINDER_INTERVAL минут.
    """
    now = datetime.now(MINSK_TZ)

    if is_quiet_hours():
        if now.hour >= QUIET_START:
            # После 21:00 — ждем до 09:00 следующего дня
            next_reminder = now.replace(
                hour=QUIET_END, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)
        else:
            # До 09:00 — ждем до 09:00 текущего дня
            next_reminder = now.replace(
                hour=QUIET_END, minute=0, second=0, microsecond=0
            )
    else:
        next_reminder = now + timedelta(minutes=REMINDER_INTERVAL)

    return next_reminder


# =====================================================================
# ФУНКЦИИ ОТПРАВКИ И УПРАВЛЕНИЯ НАПОМИНАНИЯМИ
# =====================================================================


async def send_reminder(user_id: int) -> None:
    """Отправляет напоминание пользователю."""
    if is_quiet_hours():
        return

    try:
        await bot.send_message(
            user_id,
            "Time to drink water. Stay hydrated.",
            reply_markup=create_keyboard(),
        )
        print(f"Reminder sent to user {user_id}")
    except Exception as e:
        print(f"Error while sending reminder to user {user_id}: {e}")


async def reminder_loop(user_id: int) -> None:
    """
    Бесконечный цикл отправки напоминаний для пользователя.
    Учитывает тихие часы 21:00–09:00.
    """
    print(f"Reminder loop started for user {user_id}")

    while user_reminders.get(user_id, {}).get("enabled", False):
        try:
            next_time = get_next_reminder_time()
            now = datetime.now(MINSK_TZ)
            sleep_seconds = (next_time - now).total_seconds()

            print(
                f"User {user_id}: waiting {sleep_seconds:.0f} seconds "
                f"until {next_time.strftime('%H:%M:%S')}"
            )

            await asyncio.sleep(max(1, sleep_seconds))

            if not user_reminders.get(user_id, {}).get("enabled", False):
                print(f"User {user_id} disabled reminders while waiting")
                break

            await send_reminder(user_id)

        except asyncio.CancelledError:
            print(f"Reminder loop cancelled for user {user_id}")
            break
        except Exception as e:
            print(f"Error in reminder loop for user {user_id}: {e}")
            await asyncio.sleep(5)

    print(f"Reminder loop stopped for user {user_id}")
    if user_id in user_reminders:
        user_reminders[user_id]["task"] = None


async def enable_reminders(user_id: int) -> None:
    """Включает напоминания для пользователя."""
    if user_id not in user_reminders:
        user_reminders[user_id] = {"enabled": False, "task": None}

    if user_reminders[user_id]["enabled"]:
        return

    user_reminders[user_id]["enabled"] = True
    task = asyncio.create_task(reminder_loop(user_id))
    user_reminders[user_id]["task"] = task
    print(f"Reminders enabled for user {user_id}")


async def disable_reminders(user_id: int) -> None:
    """Отключает напоминания для пользователя."""
    if user_id not in user_reminders:
        return

    user_reminders[user_id]["enabled"] = False

    task = user_reminders[user_id]["task"]
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    user_reminders[user_id]["task"] = None
    print(f"Reminders disabled for user {user_id}")


# =====================================================================
# ОБРАБОТЧИКИ СООБЩЕНИЙ
# =====================================================================


@dp.message(CommandStart())
async def start_handler(message: types.Message) -> None:
    """Обработчик команды /start."""
    user_id = message.from_user.id

    if user_id not in user_reminders:
        user_reminders[user_id] = {"enabled": False, "task": None}

    text = (
        "Water Reminder Bot\n\n"
        "This bot sends you water reminders every 90 minutes.\n\n"
        "Features:\n"
        "- Reminder interval: 90 minutes\n"
        "- Quiet hours: 21:00–09:00 (Minsk time)\n"
        "- Simple enable/disable buttons\n"
    )

    await message.answer(text, reply_markup=create_keyboard())
    print(f"New user: {user_id} ({message.from_user.first_name})")


@dp.message(F.text == "Enable reminders")
async def enable_handler(message: types.Message) -> None:
    """Обработчик кнопки 'Enable reminders'."""
    user_id = message.from_user.id

    await enable_reminders(user_id)

    await message.answer(
        "Reminders enabled.\n\n"
        "You will receive water reminders every 90 minutes "
        "between 09:00 and 21:00 (Minsk time).\n\n"
        "Press 'Disable reminders' to stop notifications.",
        reply_markup=create_keyboard(),
    )


@dp.message(F.text == "Disable reminders")
async def disable_handler(message: types.Message) -> None:
    """Обработчик кнопки 'Disable reminders'."""
    user_id = message.from_user.id

    await disable_reminders(user_id)

    await message.answer(
        "Reminders disabled.\n\n"
        "Press 'Enable reminders' to start receiving notifications again.",
        reply_markup=create_keyboard(),
    )


@dp.message()
async def echo_handler(message: types.Message) -> None:
    """Обработчик всех остальных сообщений."""
    await message.answer(
        "Use the buttons below to control reminders.",
        reply_markup=create_keyboard(),
    )


# =====================================================================
# ГЛАВНАЯ ФУНКЦИЯ
# =====================================================================


async def main() -> None:
    """Запуск бота."""
    print("\n" + "=" * 60)
    print("WATER REMINDER BOT STARTING")
    print("=" * 60)
    print(f"Reminder interval: {REMINDER_INTERVAL} minutes")
    print(f"Quiet hours: {QUIET_START}:00–{QUIET_END}:00 (Minsk time)")
    print("Timezone: Europe/Minsk")
    print("=" * 60)
    print("Bot is running. Press Ctrl+C to stop.\n")

    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
    finally:
        await bot.session.close()
        print("Bot session closed.\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete.")
