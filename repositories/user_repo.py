import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_user(
        self, telegram_id: int, name: str | None = None, phone: str | None = None
    ) -> User:
        """
        Получает пользователя по Telegram ID или создает нового, если его нет.
        """
        try:
            result = await self.session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()

            if user is None:
                logging.info(
                    f"Пользователь с Telegram ID {telegram_id} не найден. Создаем нового."
                )
                user = User(telegram_id=telegram_id, name=name, phone=phone)
                self.session.add(user)
                await self.session.commit()
                await self.session.refresh(user)
                logging.info(f"Новый пользователь создан: {user}")
            else:
                updated = False
                if name is not None and user.name != name:
                    user.name = name
                    updated = True
                if phone is not None and user.phone != phone:
                    user.phone = phone
                    updated = True

                if updated:
                    await self.session.commit()
                    logging.info(f"Данные пользователя {telegram_id} обновлены.")

            return user

        except Exception as e:
            await self.session.rollback()
            logging.error(
                f"Ошибка при получении/создании пользователя {telegram_id}: {e}"
            )
            raise

    async def get_user_by_id(self, telegram_id: int) -> User | None:
        """Получает пользователя по Telegram ID."""
        try:
            result = await self.session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logging.error(f"Ошибка при получении пользователя {telegram_id}: {e}")
            return None

    async def update_user_name(self, telegram_id: int, new_name: str) -> bool:
        """
        Обновляет имя пользователя в базе данных по Telegram ID.
        Возвращает True, если обновление прошло успешно (пользователь найден и обновлен), False иначе.
        """
        try:
            result = await self.session.execute(
                update(User)
                .where(User.telegram_id == telegram_id)
                .values(name=new_name)
                .returning(User.telegram_id)
            )
            updated_id = result.scalar_one_or_none()

            await self.session.commit()
            if updated_id is not None:
                logging.info(
                    f"Имя пользователя {telegram_id} обновлено на '{new_name}'."
                )
                return True
            else:
                logging.warning(
                    f"Попытка обновить имя пользователя {telegram_id}, но пользователь не найден."
                )
                return False
        except Exception as e:
            await self.session.rollback()
            logging.error(
                f"Ошибка при обновлении имени пользователя {telegram_id}: {e}"
            )
            return False

    async def update_user_phone(self, telegram_id: int, new_phone: str) -> bool:
        """
        Обновляет номер телефона пользователя в базе данных по Telegram ID.
        Возвращает True, если обновление прошло успешно, False иначе.
        """
        try:
            result = await self.session.execute(
                update(User)
                .where(User.telegram_id == telegram_id)
                .values(phone=new_phone)
                .returning(User.telegram_id)
            )
            updated_id = result.scalar_one_or_none()
            await self.session.commit()
            if updated_id is not None:
                logging.info(
                    f"Телефон пользователя {telegram_id} обновлен на '{new_phone}'."
                )
                return True
            else:
                logging.warning(
                    f"Попытка обновить телефон пользователя {telegram_id}, но пользователь не найден."
                )
                return False
        except Exception as e:
            await self.session.rollback()
            logging.error(
                f"Ошибка при обновлении телефона пользователя {telegram_id}: {e}"
            )
            return False
