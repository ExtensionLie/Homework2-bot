import asyncio
import logging
from datetime import date, timedelta

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN
from database import init_db, get_users_by_reminder_hour, get_homeworks_today
from handlers import student

logging.basicConfig(level=logging.INFO)

async def send_reminders(bot: Bot, hour: int):
    """Надсилає нагадування користувачам які обрали цей час."""
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    tomorrow_ua = (date.today() + timedelta(days=1)).strftime("%d.%m.%Y")
    homeworks = await get_homeworks_today(tomorrow)
    users = await get_users_by_reminder_hour(hour)

    if not homeworks or not users:
        return

    if hour < 12:
        greeting = "☀️ <b>Доброго ранку!"
    elif hour < 17:
        greeting = "🌤 <b>Доброго дня!"
    else:
        greeting = "🌙 <b>Доброго вечора!"

    lines = [f"{greeting} ДЗ на завтра ({tomorrow_ua}):</b>\n"]
    for hw in homeworks:
        lines.append(f"▪️ <b>{hw['subject']}</b> — {hw['description']}")
    lines.append("\nУдачі! 💪")
    text = "\n".join(lines)

    for user in users:
        try:
            await bot.send_message(user["telegram_id"], text, parse_mode="HTML")
        except Exception:
            pass

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(student.router)
    await init_db()

    # Запускаємо планувальник — перевіряє щогодини
    scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")
    for hour in range(5, 23):  # перевіряємо з 5:00 до 22:00
        scheduler.add_job(
            send_reminders,
            trigger="cron",
            hour=hour,
            minute=0,
            args=[bot, hour]
        )
    scheduler.start()

    print("✅ Бот запущено! Нагадування надсилаються за особистим часом кожного.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
