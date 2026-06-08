from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import Message

from db.database import async_session_factory
from keyboards.keyboards import main_menu_kb
from models.models import RegistrationStates
from repositories.user_repo import UserRepository
from services.user_service import UserService

start_router = Router()


@start_router.message(Command("start"), StateFilter(default_state))
async def cmd_start(message: Message, state: FSMContext):
    """Приветственная команда /start"""
    await state.clear()

    if not message.from_user:
        return

    user_id = message.from_user.id

    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        user_service = UserService(user_repo)

        user = await user_service.user_repo.get_user_by_id(user_id)

        if user is not None:
            await message.answer(
                f"👋 Рады видеть вас снова, {message.from_user.full_name}!\n"
                "Вы в главном меню. Выберите нужное действие:",
                reply_markup=main_menu_kb(),
            )
        else:
            await message.answer(
                "👋 Добро пожаловать! Для начала работы с ботом, пожалуйста, пройдите короткую регистрацию.\n\n"
                "Введите ваше имя:"
            )
            await state.set_state(RegistrationStates.waiting_for_name)


@start_router.message(RegistrationStates.waiting_for_name, F.text)
async def process_registration_name(message: Message, state: FSMContext):
    """Обработка ввода имени при регистрации"""
    if not message.text:
        await message.answer("⚠️ Пожалуйста, введите ваше имя текстом:")
        return

    name = message.text.strip()
    if len(name) < 2:
        await message.answer("⚠️ Имя слишком короткое. Введите настоящее имя:")
        return

    await state.update_data(chosen_name=name)
    await message.answer(
        f"Приятно познакомиться, {name}! Теперь, пожалуйста, введите ваш номер телефона:"
    )
    await state.set_state(RegistrationStates.waiting_for_phone)
