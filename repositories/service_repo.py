# repositories/service_repo.py
import logging

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import Service


class ServiceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_services(self) -> list[Service]:
        """Получает все услуги из базы данных."""
        try:
            result = await self.session.execute(select(Service).order_by(Service.name))
            return list(result.scalars().all())
        except Exception as e:
            logging.error(f"Ошибка при получении всех услуг: {e}")
            return []

    async def get_service_by_id(self, service_id: int) -> Service | None:
        """Получает услугу по ее ID."""
        try:
            result = await self.session.execute(
                select(Service).where(Service.id == service_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logging.error(f"Ошибка при получении услуги по ID {service_id}: {e}")
            return None

    async def add_service(self, name, price=None, description=None, duration=None):
        """Добавляет новую услугу в базу данных."""
        try:
            service = Service(
                name=name, price=price, description=description, duration=duration
            )
            self.session.add(service)
            await self.session.commit()
            await self.session.refresh(service)
            logging.info(f"Услуга добавлена: {service.name}")
            return service
        except Exception as e:
            await self.session.rollback()
            logging.error(f"Ошибка при добавлении услуги '{name}': {e}")
            return None

    # TODO: Добавить методы для обновления и удаления услуг
    async def delete_service(self, service_id: int) -> bool:
        """
        Удаляет услугу по ее ID из базы данных.
        Возвращает True, если услуга найдена и удалена, False иначе.
        """
        try:
            result = await self.session.execute(
                delete(Service).where(Service.id == service_id).returning(Service.id)
            )
            deleted_id = result.scalar_one_or_none()
            await self.session.commit()

            if deleted_id is not None:
                logging.info(f"Услуга ID={service_id} успешно удалена из БД.")
                return True
            else:
                logging.warning(
                    f"Попытка удаления услуги ID={service_id}, но услуга не найдена в БД."
                )
                return False
        except Exception as e:
            await self.session.rollback()
            logging.error(f"Ошибка при удалении услуги ID={service_id} из БД: {e}")
            return False

    async def update_service(self, service_id: int, updates: dict) -> bool:
        """
        Обновляет данные услуги по ее ID.
        'updates' - словарь с полями и новыми значениями (например, {'name': 'Новое название', 'price': '2000 руб'}).
        Возвращает True, если услуга найдена и обновлена, False иначе.
        """
        try:
            result = await self.session.execute(
                update(Service)
                .where(Service.id == service_id)
                .values(**updates)
                .returning(Service.id)
            )
            updated_id = result.scalar_one_or_none()
            await self.session.commit()

            if updated_id is not None:
                logging.info(
                    f"Услуга ID={service_id} успешно обновлена в БД с данными: {updates}."
                )
                return True
            else:
                logging.warning(
                    f"Попытка обновить услугу ID={service_id}, но услуга не найдена в БД."
                )
                return False
        except Exception as e:
            await self.session.rollback()
            logging.error(f"Ошибка при обновлении услуги ID={service_id} в БД: {e}")
            return False

    async def get_service_duration(self, service_id: int) -> int:
        """
        Получить длительность услуги по её ID.
        """
        result = await self.session.execute(
            select(Service.duration).where(Service.id == service_id)
        )
        duration = result.scalar()
        if duration is not None:
            return duration
        else:
            return False
