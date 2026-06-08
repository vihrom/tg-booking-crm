import logging

from models.models import User

from repositories.user_repo import UserRepository


class UserService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    async def get_user_by_id(self, telegram_id: int) -> User | None:
        """
        Бизнес-логика для получения пользователя по ID.
        """
        logging.info(f"Сервис: Попытка получить пользователя по ID {telegram_id}.")
        return await self.user_repo.get_user_by_id(telegram_id)

    async def update_user_name(self, telegram_id: int, new_name: str) -> bool:
        """
        Бизнес-логика для обновления имени пользователя.
        """
        logging.info(
            f"Сервис: Попытка обновить имя пользователя {telegram_id} на '{new_name}'."
        )
        return await self.user_repo.update_user_name(telegram_id, new_name)

    async def update_user_phone(self, telegram_id: int, new_phone: str) -> bool:
        """
        Бизнес-логика для обновления номера телефона пользователя.
        """
        logging.info(
            f"Сервис: Попытка обновить телефон пользователя {telegram_id} на '{new_phone}'."
        )
        return await self.user_repo.update_user_phone(telegram_id, new_phone)
