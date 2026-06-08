import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bot_token: str
    admin_ids: list[int]

    @property
    def ADMIN_IDS(self) -> list[int]:
        """Для обратной совместимости"""
        return self.admin_ids

    @staticmethod
    def load() -> "Config":
        token = os.getenv("BOT_TOKEN")
        if not token:
            raise ValueError("Не найден BOT_TOKEN в переменных окружения")

        admin_ids_str = os.getenv("ADMIN_IDS")
        if not admin_ids_str:
            print(
                "Предупреждение: Не найдены ADMIN_IDS в переменных окружения. Админ-панель будет недоступна."
            )
            admin_ids = []
        else:
            try:
                admin_ids = [
                    int(admin_id.strip()) for admin_id in admin_ids_str.split(",")
                ]
            except ValueError:
                raise ValueError(
                    "ADMIN_IDS должны быть перечислены через запятую как целые числа"
                )

        return Config(bot_token=token, admin_ids=admin_ids)
