import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import Message, TelegramObject

from models.models import BookingStates, RegistrationStates


class CancelMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            current_state_str = (
                await data.get("state").get_state() if data.get("state") else None
            )
            logging.info(
                f"!!! DEBUG MIDDLEWARE START !!! Сообщение от пользователя {event.from_user.id}. Текст: '{event.text}'. Тип контента: {event.content_type}. Текущее состояние (строка): {current_state_str}"
            )

        if not isinstance(event, Message):
            return await handler(event, data)

        if event.text and event.text.lower() == "/cancel":
            logging.info(
                f"Middleware: Перехвачена команда /cancel от пользователя {event.from_user.id}"
            )

            state: FSMContext | None = data.get("state")
            if state is None:
                logging.warning(
                    f"Middleware: Контекст состояния не найден для пользователя {event.from_user.id}. Невозможно проверить состояние."
                )
                return await handler(event, data)

            current_state = await state.get_state()

            main_menu_kb_func = data.get("main_menu_kb")
            if not main_menu_kb_func or not callable(main_menu_kb_func):
                logging.error(
                    "Middleware: Функция main_menu_kb не найдена в workflow_data!"
                )
                await state.clear()
                await event.answer(
                    "Действие отменено. Ошибка: Не удалось получить клавиатуру."
                )
                return

            target_states_list = list(BookingStates.__states__) + list(
                RegistrationStates.__states__
            )
            target_states_names = [str(s) for s in target_states_list]

            # --- ДЕТАЛЬНЫЙ ЛОГ ПРОВЕРКИ СОСТОЯНИЯ ---
            logging.info(
                f"DEBUG MIDDLEWARE STATE CHECK: Объект текущего состояния: {current_state}. Строка состояния: {str(current_state)}. Список целевых объектов состояний: {target_states_list}"
            )
            logging.info(
                f"DEBUG MIDDLEWARE STATE CHECK: Список целевых ИМЕН состояний (для сравнения строк): {target_states_names}"
            )

            is_in_target_fsm = current_state in target_states_list

            logging.info(
                f"Middleware: Текущее состояние пользователя {event.from_user.id}: {current_state}. Объект состояния найден в целевых: {is_in_target_fsm}"
            )

            if is_in_target_fsm:
                logging.info(
                    f"Middleware: Очистка состояния {current_state} для пользователя {event.from_user.id}."
                )
                await state.clear()
                keyboard = main_menu_kb_func()
                await event.answer("Действие отменено.", reply_markup=keyboard)
                return

            else:
                logging.info(
                    "Middleware: Команда /cancel вне целевого FSM. Передаем дальше."
                )
                return await handler(event, data)

        return await handler(event, data)
