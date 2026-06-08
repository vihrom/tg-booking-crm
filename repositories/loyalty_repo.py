from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.models import LoyaltyPoints


class LoyaltyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user_loyalty(self, user_telegram_id: int) -> LoyaltyPoints:
        """Получает или создает запись лояльности для пользователя"""
        query = select(LoyaltyPoints).where(
            LoyaltyPoints.user_telegram_id == user_telegram_id
        )
        result = await self.session.execute(query)
        loyalty = result.scalar_one_or_none()

        if not loyalty:
            loyalty = LoyaltyPoints(user_telegram_id=user_telegram_id)
            self.session.add(loyalty)
            await self.session.commit()
            await self.session.refresh(loyalty)

        return loyalty

    async def add_points(self, user_telegram_id: int, points: int, spent_amount: float):
        """Начисляет баллы за посещение"""
        loyalty = await self.get_user_loyalty(user_telegram_id)
        loyalty.points += points
        loyalty.total_spent += spent_amount

        # Обновляем уровень
        if loyalty.total_spent >= 50000:
            loyalty.level = 3  # VIP
        elif loyalty.total_spent >= 20000:
            loyalty.level = 2  # Серебряный

        await self.session.commit()
        return loyalty

    async def use_points(self, user_telegram_id: int, points: int) -> bool:
        """Списывает баллы при использовании"""
        loyalty = await self.get_user_loyalty(user_telegram_id)
        if loyalty.points >= points:
            loyalty.points -= points
            await self.session.commit()
            return True
        return False
