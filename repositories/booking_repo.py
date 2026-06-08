import logging
from datetime import date, datetime, timedelta

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from models.models import Booking


class BookingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_booking(
        self,
        name: str,
        phone: str,
        datetime_obj: datetime,
        service_id: int,
        employee_id: int | None,
        user_telegram_id: int,
    ) -> Booking | None:
        """
        Добавляет новую запись в базу данных.
        Принимает объект datetime, а не строку.
        """
        try:
            new_booking = Booking(
                name=name,
                phone=phone,
                datetime=datetime_obj,
                created_at=datetime.now(),
                service_id=service_id,
                employee_id=employee_id,
                user_telegram_id=user_telegram_id,
            )
            self.session.add(new_booking)
            await self.session.commit()
            await self.session.refresh(new_booking)
            logging.info(
                f"Запись добавлена: ID={new_booking.id}, User ID={new_booking.user_telegram_id}, Дата/Время={new_booking.datetime}, Услуга ID={new_booking.service_id}, Сотрудник ID={new_booking.employee_id}"
            )
            return new_booking
        except Exception as e:
            await self.session.rollback()
            logging.error(
                f"Ошибка при добавлении записи для пользователя {user_telegram_id}: {e}"
            )
            return None

    async def get_user_bookings(self, user_telegram_id: int) -> list[Booking]:
        """
        Получает все предстоящие записи пользователя.
        """
        try:
            now = datetime.now()
            result = await self.session.execute(
                select(Booking)
                .where(Booking.user_telegram_id == user_telegram_id)
                .where(Booking.datetime > now)
                .order_by(Booking.datetime)
            )
            bookings = list(result.scalars().all())
            return bookings
        except Exception as e:
            logging.error(
                f"Ошибка при получении записей пользователя {user_telegram_id}: {e}"
            )
            return []

    async def get_all(self) -> list[Booking]:
        """Возвращает список всех бронирований."""
        try:
            result = await self.session.execute(select(Booking).order_by(Booking.id))
            return list(result.scalars().all())
        except Exception as e:
            logging.error(f"Ошибка при получении всех бронирований: {e}")
            return []

    async def get_booking_by_id(self, booking_id: int) -> Booking | None:
        """
        Получает запись по ее уникальному ID, с жадной загрузкой User, Service и Employee.
        Используется для административной отмены и уведомления пользователя.
        """
        try:
            query = select(Booking).where(Booking.id == booking_id)
            query = query.options(
                joinedload(Booking.user),
                joinedload(Booking.service),
                joinedload(Booking.employee),
            )

            result = await self.session.execute(query)
            booking = result.scalars().first()

            logging.info(
                f"Найдена запись по ID {booking_id}: {'Да' if booking else 'Нет'} (с загруженными связями)."
            )
            return booking
        except Exception as e:
            logging.error(
                f"Ошибка при получении записи по ID {booking_id} (с загруженными связями): {e}"
            )
            return None

    async def delete_booking(self, booking_id: int) -> bool:
        """
        Удаляет запись по ее ID.
        """
        try:
            statement = (
                delete(Booking).where(Booking.id == booking_id).returning(Booking.id)
            )

            result = await self.session.execute(statement)
            deleted_id = result.scalar_one_or_none()

            await self.session.commit()

            if deleted_id is not None:
                logging.info(f"Запись ID={booking_id} успешно удалена.")
                return True
            else:
                logging.warning(
                    f"Попытка удаления записи ID={booking_id}: запись не найдена."
                )
                return False

        except Exception as e:
            await self.session.rollback()
            logging.error(msg=f"Ошибка при удалении записи ID={booking_id}: {e}")
            return False

    async def delete_user_booking(self, user_telegram_id: int, booking_id: int) -> bool:
        """
        Удаляет запись пользователя по ее ID, только если она принадлежит этому пользователю.
        """
        try:
            statement = (
                delete(Booking)
                .where(Booking.id == booking_id)
                .where(Booking.user_telegram_id == user_telegram_id)
                .returning(Booking.id)
            )

            result = await self.session.execute(statement)
            deleted_id = result.scalar_one_or_none()

            await self.session.commit()

            if deleted_id is not None:
                logging.info(
                    f"Запись ID={booking_id} пользователя {user_telegram_id} успешно удалена."
                )
                return True
            else:
                logging.warning(
                    f"Попытка удаления записи ID={booking_id} пользователя {user_telegram_id}: запись не найдена."
                )
                return False

        except Exception as e:
            await self.session.rollback()
            logging.error(msg=f"Ошибка при удалении записи ID={booking_id}: {e}")
            return False

    async def get_all_bookings(self) -> list[Booking]:
        """
        Получает все записи из базы данных, отсортированные по дате/времени.
        """
        try:
            result = await self.session.execute(
                select(Booking)
                .order_by(Booking.datetime)
                .options(joinedload(Booking.service), joinedload(Booking.employee))
            )
            bookings = list(result.scalars().all())
            logging.info(f"Найдено {len(bookings)} всех записей.")
            return bookings
        except Exception as e:
            logging.error(f"Ошибка при получении всех записей: {e}")
            return []

    async def get_employee_bookings(
        self, employee_id: int, date_obj
    ) -> list[tuple[datetime, datetime]]:
        result = await self.session.execute(
            select(Booking)
            .where(
                Booking.employee_id == employee_id,
                func.date(Booking.datetime) == date_obj,
            )
            .options(joinedload(Booking.service))
        )
        bookings = result.scalars().all()
        intervals = []
        for b in bookings:
            start = b.datetime
            duration = b.service.duration if b.service else 0
            end = start + timedelta(minutes=duration)
            intervals.append((start, end))
        return intervals

    async def get_bookings_by_employee_service_date(
        self, target_date: date, employee_id: int | None, service_id: int
    ) -> list[Booking]:
        """
        Получает все записи на определенную дату для конкретного сотрудника и услуги.
        Используется для проверки доступности временных слотов.
        """
        try:
            start_of_day = datetime.combine(target_date, datetime.min.time())
            end_of_day = datetime.combine(target_date, datetime.max.time())

            query = select(Booking).where(
                and_(
                    Booking.datetime >= start_of_day,
                    Booking.datetime <= end_of_day,
                    Booking.service_id == service_id,
                )
            )

            if employee_id is not None:
                query = query.where(Booking.employee_id == employee_id)
            # Выполняем запрос вне условия!
            result = await self.session.execute(query)
            bookings = list(result.scalars().all())
            logging.info(
                f"Найдено {len(bookings)} записей для проверки доступности на {target_date} (сотрудник: {employee_id}, услуга: {service_id})."
            )
            return bookings
        except Exception as e:
            logging.error(
                f"Ошибка при получении записей для проверки доступности на {target_date}: {e}"
            )
            return []

    async def get_bookings_by_employee_and_date(self, employee_id: int, date: date):
        """
        Возвращает все записи сотрудника на выбранную дату с подгруженной услугой (для доступа к длительности).
        """
        result = await self.session.execute(
            select(Booking)
            .where(
                Booking.employee_id == employee_id, func.date(Booking.datetime) == date
            )
            .options(joinedload(Booking.service))
        )
        return result.scalars().all()

    async def get_bookings_in_time_range(self, dt_from, dt_to):
        result = await self.session.execute(
            select(Booking).where(
                and_(Booking.datetime >= dt_from, Booking.datetime < dt_to)
            )
        )
        return result.scalars().all()
