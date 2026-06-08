from sqlalchemy import select, func
from models.models import AdminMessage, User


class MessageRepository:
    def __init__(self, session):
        self.session = session

    async def create_message(
        self,
        user_telegram_id: int,
        message_text: str,
        admin_telegram_id: int | None = None,
        is_from_admin: bool = False,
        attachment_id: str | None = None,
    ) -> AdminMessage:
        message = AdminMessage(
            user_telegram_id=user_telegram_id,
            admin_telegram_id=admin_telegram_id,
            message_text=message_text,
            is_from_admin=is_from_admin,
            attachment_id=attachment_id,
        )
        self.session.add(message)
        await self.session.commit()
        return message

    async def get_users_with_unread_messages(self):
        """Получает список пользователей с непрочитанными сообщениями"""
        query = (
            select(User, func.count(AdminMessage.id).label("unread_count"))
            .join(AdminMessage, User.telegram_id == AdminMessage.user_telegram_id)
            .where(AdminMessage.is_read == False)
            .group_by(User.telegram_id, User.name)
        )
        result = await self.session.execute(query)
        return result.all()

    async def get_user_messages(self, user_telegram_id: int, limit: int = 10):
        """Получает историю сообщений с пользователем"""
        query = (
            select(AdminMessage)
            .where(AdminMessage.user_telegram_id == user_telegram_id)
            .order_by(AdminMessage.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(reversed(result.scalars().all()))

    async def mark_messages_as_read(self, user_telegram_id: int):
        """Отмечает все сообщения пользователя как прочитанные"""
        query = select(AdminMessage).where(
            AdminMessage.user_telegram_id == user_telegram_id,
            AdminMessage.is_read == False,
        )
        result = await self.session.execute(query)
        messages = result.scalars().all()
        for message in messages:
            message.is_read = True
        await self.session.commit()

    async def save_admin_reply(
        self,
        user_telegram_id: int,
        admin_telegram_id: int,
        message_text: str,
        attachment_id: str | None = None,
    ) -> AdminMessage:
        """Сохраняет ответ админа"""
        message = AdminMessage(
            user_telegram_id=user_telegram_id,
            admin_telegram_id=admin_telegram_id,
            message_text=message_text,
            is_from_admin=True,
            attachment_id=attachment_id,
        )
        self.session.add(message)
        await self.session.commit()
        return message
