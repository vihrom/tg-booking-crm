import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
# from aiogram.fsm.storage.redis import RedisStorage, DefaultKeyBuilder

from config import Config
from db.database import async_session_factory, init_db

from handlers import admin_handlers, user_handlers
from keyboards.keyboards import main_menu_kb

from middlewares.cancel_middleware import CancelMiddleware
from utils.reminders import reminder_loop


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    try:
        config = Config.load()
    except ValueError as e:
        logging.critical(f"Ошибка загрузки конфигурации: {e}")
        return

    try:
        logging.info("Шаг: Начинаем инициализацию базы данных...")
        await init_db()
        logging.info("Шаг: База данных успешно инициализирована!")
    except Exception as e:
        logging.critical(f"Ошибка инициализации базы данных: {e}")
        return

    bot = Bot(
        token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    # TODO: Поменять на Redis
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.workflow_data["admin_ids"] = config.admin_ids
    dp.workflow_data["main_menu_kb"] = main_menu_kb

    dp.message.middleware(CancelMiddleware())

    dp.include_router(user_handlers.router)

    if config.admin_ids:
        admin_handlers.router.message.filter(F.from_user.id.in_(config.admin_ids))
        dp.include_router(admin_handlers.router)
        logging.info(f"Админские хендлеры зарегистрированы для ID: {config.admin_ids}")
    else:
        logging.warning("ADMIN_IDS не заданы, админские команды будут недоступны.")

    await bot.delete_webhook(drop_pending_updates=True)

    asyncio.create_task(reminder_loop(bot, async_session_factory))

    logging.info("Запуск бота в режиме polling...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logging.critical(f"Критическая ошибка при работе бота: {e}")
    finally:
        await bot.session.close()
        logging.info("Бот остановлен.")


asyncio.run(main(), debug=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt, SystemExit:
        logging.info("Выход по команде пользователя.")
