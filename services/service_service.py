import logging

from models.models import Service
from repositories.service_repo import ServiceRepository


class ServiceService:
    def __init__(self, service_repo: ServiceRepository):
        self.service_repo = service_repo

    async def get_all_services(self) -> list[Service]:
        """Получает все услуги через репозиторий."""
        return await self.service_repo.get_all_services()

    async def get_service_by_id(self, service_id: int) -> Service | None:
        """Получает услугу по ID через репозиторий."""
        return await self.service_repo.get_service_by_id(service_id)

    async def add_service(self, name, price=None, description=None, duration=None):
        """Добавляет новую услугу через репозиторий."""
        Service(name=name, price=price, description=description, duration=duration)
        return await self.service_repo.add_service(name, price, description, duration)

    async def delete_service(self, service_id: int) -> bool:
        """
        Бизнес-логика для удаления услуги по ID.
        Вызывает метод репозитория для удаления.
        """
        logging.info(f"Сервис: Попытка удаления услуги ID={service_id}.")
        return await self.service_repo.delete_service(service_id)

    async def update_service(self, service_id: int, updates: dict) -> bool:
        """
        Бизнес-логика для обновления данных услуги по ID.
        'updates' - словарь с полями и новыми значениями (например, {'price': '2000 руб'}).
        Вызывает метод репозитория для обновления.
        """
        logging.info(
            f"Сервис: Попытка обновления услуги ID={service_id} с данными: {updates}."
        )
        return await self.service_repo.update_service(service_id, updates)
