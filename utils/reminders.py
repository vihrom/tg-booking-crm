import asyncio
from datetime import datetime, timedelta


async def reminder_loop(bot, session_factory, interval=60):
    """
    Периодически проверяет записи и отправляет напоминания за 2 часа до процедуры.
    interval — период проверки в секундах (по умолчанию 60).
    """
    from repositories.booking_repo import BookingRepository
    from repositories.user_repo import UserRepository

    while True:
        try:
            async with session_factory() as session:
                booking_repo = BookingRepository(session)
                user_repo = UserRepository(session)
                now = datetime.now()
                remind_from = now + timedelta(hours=2)
                remind_to = now + timedelta(hours=2, minutes=1)  # Окно 1 минута

                bookings = await booking_repo.get_bookings_in_time_range(
                    remind_from, remind_to
                )
                for booking in bookings:
                    user = await user_repo.get_user_by_id(booking.user_telegram_id)
                    if user and user.telegram_id:
                        try:
                            await bot.send_message(
                                user.telegram_id,
                                f"⏰ Напоминание! Ваша запись на {booking.datetime.strftime('%d.%m.%Y %H:%M')} начнётся через 2 часа.",
                            )
                        except Exception as e:
                            import logging

                            logging.error(
                                f"Не удалось отправить напоминание пользователю {user.telegram_id}: {e}"
                            )
        except Exception as e:
            import logging

            logging.error(f"Ошибка в задаче напоминаний: {e}")

        await asyncio.sleep(interval)
