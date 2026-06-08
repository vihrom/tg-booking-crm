import logging
from datetime import date, datetime, timedelta

from models.models import Booking
from repositories.booking_repo import BookingRepository
from repositories.user_repo import UserRepository


class BookingService:
    def __init__(
        self, booking_repo: BookingRepository, user_repo: UserRepository, service_repo
    ):
        self.booking_repo = booking_repo
        self.user_repo = user_repo
        self.service_repo = service_repo

    async def create_booking(
        self,
        user_telegram_id: int,
        datetime_str: str,
        service_id: int,
        employee_id: int,
    ) -> Booking | None:
        """
        Создать запись, если время доступно.
        """
        try:
            datetime_obj = datetime.strptime(datetime_str, "%d.%m.%Y %H:%M")
        except ValueError as e:
            logging.error(f"Ошибка парсинга строки даты/времени '{datetime_str}': {e}")
            return None

        if not await self.is_time_available(employee_id, service_id, datetime_obj):
            logging.info("Время занято, запись не создаётся.")
            return None

        user = await self.user_repo.get_user_by_id(user_telegram_id)
        if not user or not user.name or not user.phone:
            logging.error(
                f"Не удалось получить данные пользователя {user_telegram_id} для записи."
            )
            return None

        return await self.booking_repo.add_booking(
            name=user.name,
            phone=user.phone,
            datetime_obj=datetime_obj,
            service_id=service_id,
            employee_id=employee_id,
            user_telegram_id=user_telegram_id,
        )

    async def list_bookings(self) -> list[Booking]:
        """Возвращает список всех бронирований (для админа)."""
        return await self.booking_repo.get_all()

    async def list_user_bookings(self, user_telegram_id: int) -> list[Booking]:
        """
        Бизнес-логика для получения списка предстоящих записей пользователя.
        """
        logging.info(
            f"Сервис: Попытка получить список записей для пользователя {user_telegram_id}."
        )
        return await self.booking_repo.get_user_bookings(user_telegram_id)

    async def delete_user_booking(self, user_telegram_id: int, booking_id: int) -> bool:
        """
        Бизнес-логика для удаления записи пользователя по ID с проверкой владельца.
        """
        logging.info(
            f"Сервис: Попытка удалить запись ID={booking_id} для пользователя {user_telegram_id}."
        )
        return await self.booking_repo.delete_user_booking(user_telegram_id, booking_id)

    async def get_booking_by_id(self, booking_id: int) -> Booking | None:
        """
        Бизнес-логика для получения записи по ее ID.
        Вызывает соответствующий метод репозитория.
        """
        logging.info(f"Сервис: Попытка получения записи по ID {booking_id}.")
        return await self.booking_repo.get_booking_by_id(booking_id)

    async def delete_booking(self, booking_id: int) -> bool:
        """
        Бизнес-логика для удаления записи по ID.
        Вызывает соответствующий метод репозитория.
        Используется для пользовательской и административной отмены.
        """
        logging.info(f"Сервис: Попытка удаления записи по ID {booking_id}.")
        return await self.booking_repo.delete_booking(booking_id)

    async def get_bookings_for_availability_check(
        self,
        target_date: date,
        employee_id: int | None,
        service_id: int,
    ) -> list[Booking]:
        """
        Бизнес-логика для получения списка занятых временных слотов на определенную дату.
        """
        logging.info(
            f"Сервис: Получение записей для проверки доступности на {target_date} (сотрудник: {employee_id}, услуга: {service_id})."
        )
        return await self.booking_repo.get_bookings_by_employee_service_date(
            target_date, employee_id, service_id
        )

    async def list_all_bookings(self) -> list[Booking]:
        """
        Бизнес-логика для получения списка всех записей (для админа).
        """
        logging.info("Сервис: Попытка получить список всех записей.")
        return await self.booking_repo.get_all_bookings()

    async def is_time_available(
        self, employee_id: int, service_id: int, start_time: datetime
    ) -> bool:
        """
        Проверить, доступно ли время для записи.
        """
        service_duration = await self.service_repo.get_service_duration(service_id)
        end_time = start_time + timedelta(minutes=service_duration)

        bookings = await self.booking_repo.get_bookings_by_employee_service_date(
            target_date=start_time.date(),
            employee_id=employee_id,
            service_id=service_id,
        )

        for booking in bookings:
            booking_end_time = booking.datetime + timedelta(
                minutes=booking.service.duration
            )
            if not (end_time <= booking.datetime or start_time >= booking_end_time):
                return False

        return True
