from repositories.loyalty_repo import LoyaltyRepository


class LoyaltyService:
    def __init__(self, loyalty_repo: LoyaltyRepository):
        self.loyalty_repo = loyalty_repo

    async def process_visit(self, user_telegram_id: int, service_price: float):
        """Обрабатывает посещение клиента"""
        points_to_add = int(service_price * 0.05)
        loyalty = await self.loyalty_repo.add_points(
            user_telegram_id, points_to_add, service_price
        )

        message = (
            f"✨ Начислено {points_to_add} баллов!\n"
            f"💰 Ваш текущий баланс: {loyalty.points} баллов\n"
            f"🏆 Ваш уровень: {self._get_level_name(loyalty.level)}\n"
        )

        if loyalty.level > 1:
            message += f"🎁 Ваша скидка: {self._get_level_discount(loyalty.level)}%"

        return message

    def _get_level_name(self, level: int) -> str:
        return {1: "Базовый", 2: "Серебряный", 3: "VIP"}.get(level, "Базовый")

    def _get_level_discount(self, level: int) -> int:
        return {
            1: 0,
            2: 5,
            3: 10,
        }.get(level, 0)

    async def get_user_status(self, user_telegram_id: int):
        """Получает информацию о статусе лояльности клиента"""
        loyalty = await self.loyalty_repo.get_user_loyalty(user_telegram_id)
        return (
            f"💎 Программа лояльности:\n\n"
            f"💰 Баланс баллов: {loyalty.points}\n"
            f"🏆 Уровень: {self._get_level_name(loyalty.level)}\n"
            f"💳 Потрачено всего: {loyalty.total_spent:.2f} руб.\n"
            f"🎁 Текущая скидка: {self._get_level_discount(loyalty.level)}%\n\n"
            f"До следующего уровня осталось:\n"
            f"{self._get_next_level_info(loyalty)}"
        )

    def _get_next_level_info(self, loyalty) -> str:
        if loyalty.level == 1:
            remaining = 20000 - loyalty.total_spent
            return f"🥈 До серебряного уровня: {remaining:.2f} руб."
        elif loyalty.level == 2:
            remaining = 50000 - loyalty.total_spent
            return f"👑 До VIP уровня: {remaining:.2f} руб."
        return "Вы достигли максимального уровня!"
