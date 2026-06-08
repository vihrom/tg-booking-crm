import logging

from sqlalchemy import and_, delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from models.models import (
    Employee,
    Service,
    employee_service_association,
)


class EmployeeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_employee(
        self, name: str, specialty: str | None = None
    ) -> Employee | None:
        """
        Добавляет нового сотрудника в базу данных.
        """
        try:
            new_employee = Employee(name=name, specialty=specialty)
            self.session.add(new_employee)
            await self.session.commit()
            await self.session.refresh(new_employee)
            logging.info(
                f"Сотрудник добавлен: ID={new_employee.id}, Имя='{new_employee.name}'"
            )
            return new_employee
        except Exception as e:
            await self.session.rollback()
            logging.error(f"Ошибка при добавлении сотрудника '{name}': {e}")
            return None

    async def get_employee_by_id(self, employee_id: int) -> Employee | None:
        """
        Получает сотрудника по его ID, с жадной загрузкой связанных услуг.
        """
        try:
            query = (
                select(Employee)
                .where(Employee.id == employee_id)
                .options(joinedload(Employee.services))
            )
            result = await self.session.execute(query)  # <-- ДОЛЖЕН БЫТЬ await здесь

            employee = result.unique().scalars().first()

            logging.info(
                f"Найден сотрудник по ID {employee_id}: {employee.name if employee else 'Не найден'} (после unique())."
            )
            return employee
        except Exception as e:
            logging.error(f"Ошибка при получении сотрудника по ID {employee_id}: {e}")
            return None

    async def get_all_employees(self) -> list[Employee]:
        """
        Получает всех сотрудников из базы данных, с жадной загрузкой связанных услуг.
        Добавлен .unique() из-за жадной загрузки коллекции услуг.
        """
        try:
            query = (
                select(Employee)
                .order_by(Employee.name)
                .options(joinedload(Employee.services))
            )
            result = await self.session.execute(query)

            employees = list(result.unique().scalars().all())

            # --- ОТЛАДОЧНЫЕ ЛОГИ ---
            logging.info(
                f"DEBUG REPO: Найдено {len(employees)} сотрудников после unique()."
            )
            unique_employee_ids = [emp.id for emp in employees]
            logging.info(
                f"DEBUG REPO: get_all_employees unique employee IDs после unique(): {unique_employee_ids}"
            )
            # --- КОНЕЦ ОТЛАДОЧНОГО ЛОГА ---

            return employees
        except Exception as e:
            logging.error(f"Ошибка при получении всех сотрудников: {e}")
            return []

    async def get_employee_services(self, employee_id: int) -> list[Service]:
        """
        Получает список услуг, связанных с определенным сотрудником, напрямую через ассоциативную таблицу.
        Это альтернатива joinedload, может быть полезно, если нужен просто список услуг без объекта сотрудника.
        """
        try:
            result = await self.session.execute(
                select(Service)
                .join(employee_service_association)
                .where(employee_service_association.c.employee_id == employee_id)
                .order_by(Service.name)
            )
            services = list(result.scalars().all())
            logging.info(
                f"Найдено {len(services)} услуг, связанных с сотрудником ID={employee_id}."
            )
            return services
        except Exception as e:
            logging.error(
                f"Ошибка при получении услуг для сотрудника ID={employee_id}: {e}"
            )
            return []

    async def add_employee_service_association(
        self, employee_id: int, service_id: int
    ) -> bool:
        """
        Добавляет связь между сотрудником и услугой в ассоциативную таблицу.
        Возвращает True, если связь успешно добавлена (или уже существует), False иначе (ошибка).
        Предполагается, что в ассоциативной таблице есть уникальное ограничение на employee_id + service_id.
        """
        try:
            await self.session.execute(
                insert(employee_service_association).values(
                    employee_id=employee_id, service_id=service_id
                )
            )
            await self.session.commit()
            logging.info(
                f"Связь добавлена/существовала: Сотрудник ID={employee_id}, Услуга ID={service_id}."
            )
            return True

        except Exception as e:
            await self.session.rollback()
            if "UNIQUE constraint failed" in str(e):
                logging.warning(
                    f"Попытка добавить существующую связь (дубликат): Сотрудник ID={employee_id}, Услуга ID={service_id}."
                )
                return False
            else:
                logging.error(
                    f"Ошибка при добавлении связи (Сотрудник ID={employee_id}, Услуга ID={service_id}): {e}"
                )
                return False

    async def remove_employee_service_association(
        self, employee_id: int, service_id: int
    ) -> bool:
        """
        Удаляет связь между сотрудником и услугой из ассоциативной таблицы.
        Возвращает True, если связь найдена и удалена, False иначе.
        """
        try:
            result = await self.session.execute(
                delete(employee_service_association)
                .where(
                    and_(
                        employee_service_association.c.employee_id == employee_id,
                        employee_service_association.c.service_id == service_id,
                    )
                )
                .returning(employee_service_association.c.service_id)
            )
            deleted_id = result.scalar_one_or_none()
            await self.session.commit()

            if deleted_id is not None:
                logging.info(
                    f"Связь удалена: Сотрудник ID={employee_id}, Услуга ID={service_id}."
                )
                return True
            else:
                logging.warning(
                    f"Попытка удалить несуществующую связь: Сотрудник ID={employee_id}, Услуга ID={service_id}."
                )
                return False
        except Exception as e:
            await self.session.rollback()
            logging.error(
                f"Ошибка при удалении связи (Сотрудник ID={employee_id}, Услуга ID={service_id}): {e}"
            )
            return False

    async def get_employees_by_service_id(self, service_id: int) -> list[Employee]:
        """
        Получает список сотрудников, которые предоставляют определенную услугу.
        Используется в процессе записи пользователя.
        Добавлен .unique() для безопасности при работе с JOIN на коллекцию.
        """
        try:
            query = (
                select(Employee)
                .join(employee_service_association)
                .where(employee_service_association.c.service_id == service_id)
                .order_by(Employee.name)
            )
            result = await self.session.execute(query)  # <-- Асинхронное выполнение

            employees = list(result.unique().scalars().all())

            logging.info(
                f"Найдено {len(employees)} сотрудников для услуги ID={service_id}."
            )
            return employees
        except Exception as e:
            logging.error(
                f"Ошибка при получении сотрудников для услуги ID={service_id}: {e}"
            )
            return []

    #
    async def update_employee(self, employee_id: int, updates: dict) -> bool:
        """
        Обновляет данные сотрудника по его ID.
        'updates' - словарь с полями и новыми значениями (например, {'name': 'Новое имя', 'specialty': 'Новая специальность'}).
        Возвращает True, если сотрудник найден и обновлен, False иначе.
        """
        try:
            result = await self.session.execute(
                update(Employee)
                .where(Employee.id == employee_id)
                .values(**updates)
                .returning(Employee.id)
            )
            update_id = result.scalar_one_or_none()
            await self.session.commit()

            if update_id is not None:
                logging.info(
                    f"Сотрудник ID={employee_id} успешно обновлен в БД с данными: {updates}."
                )
                return True
            else:
                logging.warning(
                    f"Попытка обновить сотрудника ID={employee_id}, но сотрудник не найден."
                )
                return False
        except Exception as e:
            await self.session.rollback()
            logging.error(
                f"Ошибка при обновлении сотрудника ID={employee_id} в БД: {e}"
            )
            return False

    async def delete_employee(self, employee_id: int) -> bool:
        """
        Удаляет сотрудника по его ID из базы данных.
        Возвращает True, если сотрудник найден и удален, False иначе.
        """
        try:
            result = await self.session.execute(
                delete(Employee)
                .where(Employee.id == employee_id)
                .returning(Employee.id)
            )
            deleted_id = result.scalar_one_or_none()
            await self.session.commit()

            if deleted_id is not None:
                logging.info(f"Сотрудник ID={employee_id} успешно удален из БД.")
                return True
            else:
                logging.warning(
                    f"Попытка удаления сотрудника ID={employee_id}, но сотрудник не найден в БД."
                )
                return False
        except Exception as e:
            await self.session.rollback()
            logging.error(f"Ошибка при удалении сотрудника ID={employee_id} из БД: {e}")
            return False
