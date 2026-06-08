import logging

from sqlalchemy import select

from models.models import Employee, EmployeeSchedule, Service
from repositories.employee_repo import EmployeeRepository


class EmployeeService:
    def __init__(self, employee_repo: EmployeeRepository):
        self.employee_repo = employee_repo

    async def add_employee(
        self, name: str, specialty: str | None = None
    ) -> Employee | None:
        """
        Бизнес-логика для добавления нового сотрудника.
        """
        logging.info(f"Сервис: Попытка добавить сотрудника '{name}'.")
        return await self.employee_repo.add_employee(name, specialty)

    async def get_employee_by_id(self, employee_id: int) -> Employee | None:
        """
        Бизнес-логика для получения сотрудника по ID (с загрузкой услуг).
        """
        logging.info(f"Сервис: Попытка получить сотрудника по ID {employee_id}.")
        return await self.employee_repo.get_employee_by_id(employee_id)

    async def get_all_employees(self) -> list[Employee]:
        """
        Бизнес-логика для получения всех сотрудников (с загрузкой услуг).
        """
        logging.info("Сервис: Попытка получить всех сотрудников.")
        return await self.employee_repo.get_all_employees()

    async def get_employees_by_service_id(self, service_id: int) -> list[Employee]:
        """
        Бизнес-логика для получения сотрудников, связанных с определенной услугой.
        """
        logging.info(
            f"Сервис: Попытка получить сотрудников для услуги ID {service_id}."
        )
        return await self.employee_repo.get_employees_by_service_id(service_id)

    async def get_services_for_employee(self, employee_id: int) -> list[Service]:
        """
        Бизнес-логика для получения списка услуг, связанных с сотрудником.
        """
        logging.info(
            f"Сервис: Попытка получить услуги для сотрудника ID={employee_id}."
        )
        return await self.employee_repo.get_employee_services(employee_id)

    async def add_service_to_employee(self, employee_id: int, service_id: int) -> bool:
        """
        Бизнес-логика для добавления услуги сотруднику (создание связи).
        """
        logging.info(
            f"Сервис: Попытка добавить услугу ID={service_id} сотруднику ID={employee_id}."
        )
        return await self.employee_repo.add_employee_service_association(
            employee_id, service_id
        )

    async def remove_service_from_employee(
        self, employee_id: int, service_id: int
    ) -> bool:
        """
        Бизнес-логика для удаления услуги у сотрудника (удаление связи).
        """
        logging.info(
            f"Сервис: Попытка удалить услугу ID={service_id} у сотрудника ID={employee_id}."
        )
        return await self.employee_repo.remove_employee_service_association(
            employee_id, service_id
        )

    async def update_employee(self, employee_id: int, updates: dict) -> bool:
        """
        Бизнес-логика для обновления данных сотрудника по ID.
        'updates' - словарь с полями и новыми значениями.
        """
        logging.info(
            f"Сервис: Попытка обновления сотрудника ID={employee_id} с данными: {updates}."
        )
        return await self.employee_repo.update_employee(employee_id, updates)

    async def delete_employee(self, employee_id: int) -> bool:
        """
        Бизнес-логика для удаления сотрудника по ID.
        """
        logging.info(f"Сервис: Попытка удаления сотрудника ID={employee_id}.")
        return await self.employee_repo.delete_employee(employee_id)

    async def get_employee_schedule(
        self, employee_id: int, weekday: int
    ) -> list[tuple[str, str]]:
        """
        Возвращает список рабочих интервалов сотрудника на указанный день недели.
        Пример: [('09:00', '13:00'), ('14:00', '18:00')]
        """
        session = self.employee_repo.session
        result = await session.execute(
            select(EmployeeSchedule).where(
                EmployeeSchedule.employee_id == employee_id,
                EmployeeSchedule.weekday == weekday,
            )
        )
        schedules = result.scalars().all()
        return [(str(s.start_time), str(s.end_time)) for s in schedules]
