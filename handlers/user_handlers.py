import logging
import re
from datetime import date, datetime, timedelta

from config import Config

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, default_state
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from db.database import async_session_factory
from keyboards.keyboards import (
    create_employee_selection_keyboard,
    create_my_bookings_keyboard,
    create_service_selection_keyboard,
    main_menu_kb,
)

from models.models import BookingStates, ProfileStates, RegistrationStates, ChatStates

from repositories.booking_repo import BookingRepository
from repositories.employee_repo import EmployeeRepository
from repositories.service_repo import ServiceRepository
from repositories.user_repo import UserRepository
from repositories.message_repo import MessageRepository
from repositories.loyalty_repo import (
    LoyaltyRepository,
)

from services.booking_service import BookingService
from services.employee_service import EmployeeService
from services.service_service import ServiceService
from services.user_service import UserService
from services.loyalty_service import LoyaltyService  # <-- Новый сервис лояльности
from utils.slots import get_available_days_for_employee


config = Config.load()

router = Router()


@router.message(RegistrationStates.waiting_for_name, F.text, ~Command("cancel"))
async def reg_get_name(message: Message, state: FSMContext):
    """Принимает имя пользователя во время регистрации."""
    logging.info(
        f"DEBUG REG NAME: Получено текстовое сообщение в waiting_for_name от {message.from_user.id}. Не команда /cancel."
    )

    if not message.text or len(message.text.strip()) < 2:
        await message.answer("Пожалуйста, введите ваше имя (минимум 2 символа).")
        return

    name = message.text.strip()
    await state.update_data(reg_name=name)

    await message.answer(
        "Отлично! Теперь, пожалуйста, введите ваш номер телефона (например: +79123456789 или 89123456789)."
    )
    await state.set_state(RegistrationStates.waiting_for_phone)


@router.message(RegistrationStates.waiting_for_phone, F.text, ~Command("cancel"))
async def reg_get_phone(message: Message, state: FSMContext):
    """Принимает номер телефона во время регистрации и завершает процесс."""
    logging.info(
        f"DEBUG REG PHONE: Получено текстовое сообщение в waiting_for_phone от {message.from_user.id}. Не команда /cancel."
    )

    phone = message.text.strip()
    if not re.fullmatch(r"\+?\d{10,15}", phone):
        await message.answer(
            "Пожалуйста, введите корректный номер телефона в формате +79123456789 или 89123456789."
        )
        return

    user_data = await state.get_data()
    name = user_data.get("reg_name")

    if not name:
        logging.error(
            f"Ошибка FSM регистрации: имя не найдено в данных состояния для пользователя {message.from_user.id}"
        )
        await message.answer(
            "Произошла ошибка при регистрации. Пожалуйста, попробуйте начать заново с команды /start."
        )
        await state.clear()
        return

    user_telegram_id = message.from_user.id

    try:
        async with async_session_factory() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_or_create_user(
                telegram_id=user_telegram_id, name=name, phone=phone
            )

        if user:
            await message.answer(
                f"✅ Поздравляю, {name}! Вы успешно зарегистрированы. Теперь вы можете пользоваться ботом.",
                reply_markup=main_menu_kb(),
            )
            logging.info(
                f"Пользователь {user_telegram_id} успешно зарегистрирован с именем '{name}' и телефоном '{phone}'."
            )
            await state.clear()
        else:
            logging.error(
                f"Ошибка при сохранении данных пользователя {user_telegram_id} в БД во время регистрации."
            )
            await message.answer(
                "Произошла ошибка при сохранении ваших данных. Пожалуйста, попробуйте позже."
            )

    except Exception as e:
        logging.error(
            f"Критическая ошибка при регистрации пользователя {user_telegram_id}: {e}"
        )
        await message.answer(
            "Произошла непредвиденная ошибка при регистрации. Пожалуйста, попробуйте позже."
        )


@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    """Обработчик команды /start."""
    await state.clear()

    user_telegram_id = message.from_user.id

    try:
        async with async_session_factory() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_user_by_id(user_telegram_id)

        if user:
            logging.info(f"Существующий пользователь {user_telegram_id} запустил бота.")
            await message.answer(
                "С возвращением! Выберите действие из меню:",
                reply_markup=main_menu_kb(),
            )

        else:
            logging.info(
                f"Новый пользователь {user_telegram_id}. Начинаем процесс регистрации."
            )
            await message.answer(
                "Привет! 👋 Похоже, вы у нас впервые. Для дальнейшей работы необходимо зарегистрироваться.\n"
                "Как вас зовут? (Для отмены регистрации введите /cancel)"  # Добавляем возможность отмены
            )
            await state.set_state(RegistrationStates.waiting_for_name)

    except Exception as e:
        logging.error(
            f"Ошибка при проверке регистрации пользователя {user_telegram_id} во время /start: {e}"
        )
        await message.answer(
            "Произошла ошибка при запуске бота. Пожалуйста, попробуйте позже."
        )


async def help_cmd_handler(message: Message):
    """Обработчик команды /help."""
    await message.answer(
        "Основные команды и кнопки:\n\n"
        "📝 Записаться — начать процесс записи\n"
        "🗓 Мои записи — показать ваши предстоящие записи\n"
        "💸 Цены — список цен на услуги\n"
        "❓ Помощь — показать это сообщение\n"
        "👤 Мой профиль — показать информацию о вашем профиле\n"
        "\n"
        "Также работают команды:\n"
        "/start — перезапустить бота\n"
        "/my_bookings — показать ваши записи\n"
        "/prices — список цен\n"
        "/cancel — отменить ввод данных для записи\n"
        "/profile — показать информацию о вашем профиле"
    )


@router.message(Command("my_bookings"))
async def my_bookings_cmd_handler(message: Message):
    """Обработчик команды /my_bookings."""
    user_telegram_id = message.from_user.id

    try:
        async with async_session_factory() as session:
            booking_repo = BookingRepository(session)
            user_repo = UserRepository(session)
            service_repo = ServiceRepository(session)
            service = BookingService(booking_repo, user_repo, service_repo)

            upcoming_bookings = await service.list_user_bookings(user_telegram_id)

        if not upcoming_bookings:
            await message.answer("У вас пока нет предстоящих записей.")
            return

        keyboard = create_my_bookings_keyboard(upcoming_bookings)
        response_text = "🗓 Ваши предстоящие записи (нажмите 'Отменить' для удаления):"
        await message.answer(response_text, reply_markup=keyboard)

    except Exception as e:
        logging.error(
            f"Ошибка при получении списка предстоящих бронирований пользователя {user_telegram_id}: {e}"
        )
        await message.answer("Произошла ошибка при получении ваших записей.")


@router.message(StateFilter(BookingStates))
async def temp_debug_booking_state_messages(message: Message, state: FSMContext):
    """
    Перехватывает любое сообщение в любом состоянии BookingState.
    Сообщает пользователю, что нужно завершить или отменить текущую запись.
    """
    await message.answer(
        "Пожалуйста, завершите или отмените текущую запись, чтобы продолжить другие действия. Для отмены используйте команду /cancel или кнопку 'Отменить'."
    )
    current_state = await state.get_state()
    logging.info(
        f"BOOKING STATE BLOCK: Сообщение '{message.text}' (тип: {message.content_type}) получено в состоянии {current_state} от пользователя {message.from_user.id}"
    )


@router.message(StateFilter(BookingStates, RegistrationStates), Command("cancel"))
async def cancel_fsm_cmd_handler(message: Message, state: FSMContext):
    """Обработка команды /cancel для выхода из FSM (любого FSM состояния)."""
    current_state = await state.get_state()
    logging.info(
        f"DEBUG CANCEL (ORIGINAL): Attempting to cancel from state: {current_state} for user {message.from_user.id}"
    )
    if current_state is None:
        logging.info(
            f"DEBUG CANCEL (ORIGINAL): Cancel command received for user {message.from_user.id}, but state is None."
        )
        await message.answer("У вас нет активного действия, которое можно отменить.")
        return
    logging.info(
        f"DEBUG CANCEL (ORIGINAL): Отмена состояния FSM {current_state} для пользователя {message.from_user.id} через команду /cancel."
    )
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=main_menu_kb())


@router.message(Command("profile"))
async def profile_cmd_handler(message: Message, state: FSMContext):
    """
    Обработчик команды /profile. Показывает профиль пользователя и кнопки для редактирования.
    """
    user_telegram_id = message.from_user.id
    logging.info(f"Пользователь {user_telegram_id} запросил профиль.")

    user = None
    try:
        async with async_session_factory() as session:
            user_repo = UserRepository(session)
            user_service = UserService(user_repo)
            user = await user_service.get_user_by_id(user_telegram_id)

    except Exception as e:
        logging.error(
            f"Ошибка при получении профиля пользователя {user_telegram_id}: {e}"
        )
        await message.answer("Произошла ошибка при загрузке вашего профиля.")
        return

    if not user:
        # Если пользователь не найден (не зарегистрирован)
        logging.warning(
            f"Пользователь {user_telegram_id} запросил профиль, но не найден в БД."
        )
        await message.answer(
            "Ваш профиль не найден. Пожалуйста, начните с команды /start для регистрации."
        )
        return

    profile_text = (
        f"👤 **Ваш профиль:**\n\n"
        f"**Telegram ID:** `{user.telegram_id}`\n"  # Показываем Telegram ID моноширинным шрифтом
        f"**Имя:** {user.name if user.name else 'Не указано'}\n"
        f"**Телефон:** {user.phone if user.phone else 'Не указан'}\n\n"
        f"Здесь вы можете изменить свои данные."
    )

    edit_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Изменить имя", callback_data="edit_profile_name"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Изменить телефон", callback_data="edit_profile_phone"
                )
            ],
        ]
    )

    await message.answer(
        profile_text, parse_mode="Markdown", reply_markup=edit_keyboard
    )


@router.message(Command("cancel"))
async def fallback_cancel_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    booking_states = [
        v.state for v in vars(BookingStates).values() if isinstance(v, State)
    ]
    registration_states = [
        v.state for v in vars(RegistrationStates).values() if isinstance(v, State)
    ]
    is_in_target_fsm = (
        current_state in booking_states or current_state in registration_states
    )
    logging.info(
        f"DEBUG FALLBACK CANCEL: /cancel команда получена от пользователя {message.from_user.id}. Текущее состояние: {current_state}. В целевом FSM: {is_in_target_fsm}"
    )
    if is_in_target_fsm:
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=main_menu_kb())
        logging.info(f"DEBUG FALLBACK CANCEL: Состояние FSM {current_state} очищено.")
    else:
        logging.info(
            f"DEBUG FALLBACK CANCEL: Пользователь не в целевом FSM. Состояние: {current_state}. Ничего не отменяем."
        )


@router.message(F.text == "📝 Записаться")
async def booking_start_button_handler(message: Message, state: FSMContext):
    """Обработчик нажатия кнопки '📝 Записаться'. Начинает новый процесс записи."""
    user_telegram_id = message.from_user.id
    try:
        async with async_session_factory() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_user_by_id(user_telegram_id)
        if not user:
            logging.info(
                f"Незарегистрированный пользователь {user_telegram_id} нажал 'Записаться'."
            )
            await message.answer(
                "Пожалуйста, сначала зарегистрируйтесь, чтобы сделать запись. Начните с команды /start."
            )
            await state.clear()
            return
        logging.info(
            f"Зарегистрированный пользователь {user_telegram_id} нажал 'Записаться'. Начинаем процесс записи: выбор услуги."
        )
        await state.clear()

        await state.update_data(user_telegram_id=user_telegram_id)

        async with async_session_factory() as session:
            service_repo = ServiceRepository(session)
            service_service = ServiceService(service_repo)
            services = await service_service.get_all_services()
        if not services:
            await message.answer(
                "К сожалению, сейчас нет доступных услуг для записи. Пожалуйста, попробуйте позже.",
                reply_markup=main_menu_kb(),
            )
            await state.clear()
            return

        keyboard = create_service_selection_keyboard(services)

        await message.answer("Выберите услугу для записи:", reply_markup=keyboard)
        await state.set_state(BookingStates.waiting_for_service)

    except Exception as e:
        logging.error(
            f"Ошибка при подготовке к выбору услуги для пользователя {user_telegram_id}: {e}"
        )
        await message.answer(
            "Произошла ошибка при подготовке к записи. Пожалуйста, попробуйте позже.",
            reply_markup=main_menu_kb(),
        )
        await state.clear()


@router.message(F.text == "❓ Помощь")
async def help_button_handler(message: Message):
    """Обработчик нажатия кнопки '❓ Помощь'."""
    await help_cmd_handler(message)


@router.message(F.text == "📍 Контакты", StateFilter(default_state))
async def user_contacts_cmd(message: Message):
    async with async_session_factory() as session:
        from repositories.contacts_repo import ContactsRepository
        from services.contacts_service import ContactsService

        repo = ContactsRepository(session)
        service = ContactsService(repo)
        contacts = await service.get_contacts()
        if not contacts:
            await message.answer("Контактная информация временно недоступна.")
            return
        contact_info = (
            f"📍 <b>Наш адрес:</b>\n{contacts.address}\n\n"
            f"📝 <b>О нас:</b>\n{contacts.about}\n\n"
            f"📞 <b>Телефон контактного центра:</b>\n{contacts.phone}\n\n"
            f"📧 <b>Электронная почта:</b>\n{contacts.email}\n\n"
            f'🗺️ <b>Найти нас на карте:</b>\n<a href="{contacts.map_url}">Показать на карте</a>'
        )
        await message.answer(
            contact_info, parse_mode="HTML", reply_markup=main_menu_kb()
        )


@router.message(F.text == "👤 Мой профиль")
async def profile_button_handler(message: Message, state: FSMContext):
    """Обработчик нажатия кнопки '👤 Мой профиль'."""
    logging.info(f"Пользователь {message.from_user.id} нажал кнопку 'Мой профиль'.")
    await profile_cmd_handler(message, state)


@router.message(F.text == "💸 Цены", StateFilter(default_state))
async def user_prices_cmd(message: Message):
    """
    Обрабатывает нажатие кнопки 'Цены' или текстовое сообщение 'Цены'.
    Отправляет пользователю список услуг с ценами и описанием, используя HTML форматирование.
    """
    user_id = message.from_user.id
    logging.info(f"Пользователь {user_id} запросил список цен с описанием.")

    services = []
    try:
        async with async_session_factory() as session:
            service_repo = ServiceRepository(session)
            service_service = ServiceService(service_repo)
            services = await service_service.get_all_services()

    except Exception as e:
        logging.error(
            f"Ошибка при получении списка услуг для пользователя {user_id} (цены с описанием): {e}"
        )
        await message.answer(
            "Произошла ошибка при загрузке списка услуг. Пожалуйста, попробуйте позже.",
            reply_markup=main_menu_kb(),
        )
        return

    if not services:
        price_list_message = "💉 Пока нет доступных услуг с ценами."
    else:
        price_list_message = "💉 <b>Наши услуги и цены:</b>\n\n"
        services.sort(key=lambda s: s.name)

        for service in services:
            price_display = service.price if service.price else "Цена не указана"
            price_list_message += f"- <b>{service.name}</b>: {price_display}\n"
            if service.description:
                price_list_message += f"  <i>{service.description}</i>\n"
            price_list_message += "\n"

    await message.answer(
        price_list_message, parse_mode="HTML", reply_markup=main_menu_kb()
    )


@router.message(F.text == "🗓 Мои записи")
async def my_bookings_button_handler(message: Message):
    """Обработчик нажатия кнопки '🗓 Мои записи'."""
    await my_bookings_cmd_handler(message)


@router.message(
    StateFilter(BookingStates, RegistrationStates), F.text.casefold() == "отмена"
)
async def cancel_fsm_text_handler(message: Message, state: FSMContext):
    """Обработка текста 'отмена' для выхода из FSM (любого состояния регистрации или записи)."""
    current_state = await state.get_state()
    if current_state is None:
        return
    logging.info(
        f"Отмена состояния FSM {current_state} для пользователя {message.from_user.id} через текст."
    )
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=main_menu_kb())


@router.callback_query(F.data == "edit_profile_name")
async def edit_profile_name_callback_handler(query: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие inline кнопки "Изменить имя".
    Переводит в состояние ожидания нового имени ProfileStates.waiting_for_new_name.
    """
    user_telegram_id = query.from_user.id
    logging.info(
        f"Пользователь {user_telegram_id} нажал 'Изменить имя'. Переход в ProfileStates.waiting_for_new_name."
    )

    await state.clear()  # Очищаем предыдущее состояние FSM

    await query.message.edit_text("Введите ваше новое имя:")
    await state.set_state(
        ProfileStates.waiting_for_new_name
    )  # Устанавливаем новое состояние

    # --- ОТЛАДОЧНЫЙ ЛОГ ---
    current_state_after_set = await state.get_state()
    logging.info(
        f"DEBUG PROFILE: Состояние установлено в {current_state_after_set} для пользователя {user_telegram_id}."
    )
    # --- КОНЕЦ ОТЛАДОЧНОГО ЛОГА ---

    await query.answer("Ожидаю новое имя.", show_alert=False)


@router.callback_query(F.data == "edit_profile_phone")
async def edit_profile_phone_callback_handler(query: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие inline кнопки "Изменить телефон".
    Переводит в состояние ожидания нового телефона ProfileStates.waiting_for_new_phone.
    """
    user_telegram_id = query.from_user.id
    logging.info(
        f"Пользователь {user_telegram_id} нажал 'Изменить телефон'. Переход в ProfileStates.waiting_for_new_phone."
    )

    await state.clear()

    await query.message.edit_text("Введите ваш новый номер телефона:")
    await state.set_state(ProfileStates.waiting_for_new_phone)

    # --- ОТЛАДОЧНЫЙ ЛОГ ---
    current_state_after_set = await state.get_state()
    logging.info(
        f"DEBUG PROFILE: Состояние установлено в {current_state_after_set} для пользователя {user_telegram_id}."
    )
    # --- КОНЕЦ ОТЛАДОЧНОГО ЛОГА ---

    await query.answer("Ожидаю новый номер телефона.", show_alert=False)


@router.message(ProfileStates.waiting_for_new_name, F.text)
async def process_new_name(message: Message, state: FSMContext):
    """
    Обрабатывает ввод нового имени пользователя.
    Сохраняет имя, очищает состояние и показывает обновленный профиль.
    """
    # --- ОТЛАДОЧНЫЙ ЛОГ В НАЧАЛЕ ХЕНДЛЕРА ---
    current_state = await state.get_state()
    logging.info(
        f"DEBUG PROFILE HANDLER: Вход в process_new_name для пользователя {message.from_user.id}. Текущее состояние: {current_state}. Текст сообщения: '{message.text}'"
    )
    # --- КОНЕЦ ОТЛАДОЧНОГО ЛОГА ---

    user_telegram_id = message.from_user.id
    new_name = message.text.strip()

    try:
        async with async_session_factory() as session:
            user_repo = UserRepository(session)
            user_service = UserService(user_repo)
            updated = await user_service.update_user_name(user_telegram_id, new_name)

        if updated:
            await message.answer("✅ Ваше имя успешно обновлено!")
            logging.info(
                f"Имя пользователя {user_telegram_id} обновлено через FSM профиля."
            )
            user = await user_service.get_user_by_id(user_telegram_id)
            profile_text = (
                f"👤 **Ваш обновленный профиль:**\n\n"
                f"**Telegram ID:** `{user.telegram_id}`\n"
                f"**Имя:** {user.name if user.name else 'Не указано'}\n"
                f"**Телефон:** {user.phone if user.phone else 'Не указан'}\n\n"
                f"Здесь вы можете изменить свои данные."
            )
            edit_keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✏️ Изменить имя", callback_data="edit_profile_name"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="✏️ Изменить телефон",
                            callback_data="edit_profile_phone",
                        )
                    ],
                ]
            )
            await message.answer(
                profile_text, parse_mode="Markdown", reply_markup=edit_keyboard
            )
        else:
            logging.warning(
                f"Не удалось обновить имя пользователя {user_telegram_id} (update_user_name вернул False)."
            )
            await message.answer(
                "Не удалось обновить ваше имя. Попробуйте еще раз или свяжитесь с администратором."
            )

    except Exception as e:
        logging.error(
            f"Критическая ошибка при сохранении нового имени для пользователя {user_telegram_id}: {e}"
        )
        await message.answer(
            "Произошла ошибка при обработке вашего имени. Попробуйте еще раз или начните заново /start."
        )
    finally:
        await state.clear()
        logging.info(
            f"Состояние FSM профиля очищено для пользователя {user_telegram_id}."
        )
        await message.answer(
            "Вы вышли из режима редактирования.", reply_markup=main_menu_kb()
        )


@router.message(ProfileStates.waiting_for_new_phone, F.text)
async def process_new_phone(message: Message, state: FSMContext):
    """
    Обрабатывает ввод нового номера телефона пользователя.
    Сохраняет номер, очищает состояние и показывает обновленный профиль.
    """
    # --- ОТЛАДОЧНЫЙ ЛОГ В НАЧАЛЕ ХЕНДЛЕРА ---
    current_state = await state.get_state()
    logging.info(
        f"DEBUG PROFILE HANDLER: Вход в process_new_phone для пользователя {message.from_user.id}. Текущее состояние: {current_state}. Текст сообщения: '{message.text}'"
    )
    # --- КОНЕЦ ОТЛАДОЧНОГО ЛОГА ---

    user_telegram_id = message.from_user.id
    new_phone = message.text.strip()

    updated = False
    try:
        async with async_session_factory() as session:
            user_repo = UserRepository(session)
            user_service = UserService(user_repo)
            updated = await user_service.update_user_phone(user_telegram_id, new_phone)

        if updated:
            await message.answer("✅ Ваш номер телефона успешно обновлен!")
            logging.info(
                f"Телефон пользователя {user_telegram_id} обновлен через FSM профиля."
            )
            user = await user_service.get_user_by_id(user_telegram_id)

            profile_text = (
                f"👤 **Ваш обновленный профиль:**\n\n"
                f"**Telegram ID:** `{user.telegram_id}`\n"
                f"**Имя:** {user.name if user.name else 'Не указано'}\n"
                f"**Телефон:** {user.phone if user.phone else 'Не указан'}\n\n"
                f"Здесь вы можете изменить свои данные."
            )
            edit_keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✏️ Изменить имя", callback_data="edit_profile_name"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="✏️ Изменить телефон",
                            callback_data="edit_profile_phone",
                        )
                    ],
                ]
            )
            await message.answer(
                profile_text, parse_mode="Markdown", reply_markup=edit_keyboard
            )

        else:
            logging.warning(
                f"Не удалось обновить телефон пользователя {user_telegram_id} (update_user_phone вернул False)."
            )
            await message.answer(
                "Не удалось обновить ваш номер телефона. Попробуйте еще раз или свяжитесь с администратором."
            )

    except Exception as e:
        logging.error(
            f"Критическая ошибка при сохранении нового телефона для пользователя {user_telegram_id}: {e}"
        )
        await message.answer(
            "Произошла ошибка при сохранении вашего номера телефона. Попробуйте еще раз или начните заново /start."
        )
    finally:
        await state.clear()
        logging.info(
            f"Состояние FSM профиля очищено для пользователя {user_telegram_id}."
        )
        await message.answer(
            "Вы вышли из режима редактирования.", reply_markup=main_menu_kb()
        )


@router.callback_query(
    BookingStates.waiting_for_service, F.data.startswith("select_service_")
)
async def process_service_selection(query: CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор услуги из inline клавиатуры.
    Получает сотрудников, связанных с выбранной услугой, и предлагает их выбрать.
    """
    service_id_str = query.data.split("_")[2]

    try:
        service_id = int(service_id_str)
    except ValueError:
        logging.warning(
            f"Получен неверный ID услуги из callback: {query.data} для пользователя {query.from_user.id}"
        )
        await query.answer("Неверный формат ID услуги.", show_alert=True)
        return

    selected_service = None
    available_employees = []  # Список сотрудников для выбранной услуги

    try:
        async with async_session_factory() as session:
            service_repo = ServiceRepository(session)
            service_service = ServiceService(service_repo)
            employee_repo = EmployeeRepository(session)
            employee_service = EmployeeService(employee_repo)
            selected_service = await service_service.get_service_by_id(service_id)
            available_employees = await employee_service.get_employees_by_service_id(
                service_id
            )

        if selected_service:
            await state.update_data(
                selected_service_id=selected_service.id,
                selected_service_name=selected_service.name,
            )
            if not available_employees:
                logging.warning(
                    f"Нет доступных сотрудников для услуги ID {service_id} ('{selected_service.name}')."
                )
                await query.answer(
                    "Для этой услуги нет доступных сотрудников. Пожалуйста, выберите другую услугу.",
                    show_alert=True,
                )
                services = await service_service.get_all_services()
                keyboard = create_service_selection_keyboard(services)
                await query.message.edit_text(
                    f"Вы выбрали услугу: <b>{selected_service.name}</b>.\nК сожалению, сейчас нет доступных сотрудников.\n\nВыберите другую услугу:",
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                return

            keyboard = create_employee_selection_keyboard(available_employees)

            await query.message.edit_text(
                f"Вы выбрали услугу: <b>{selected_service.name}</b>.\n\nТеперь выберите сотрудника:",
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            await state.set_state(BookingStates.waiting_for_employee)

        else:
            logging.warning(
                f"Пользователь {query.from_user.id} выбрал несуществующую услугу ID {service_id}."
            )
            await query.answer(
                "Выбранная услуга не найдена. Пожалуйста, выберите из списка.",
                show_alert=True,
            )

    except Exception as e:
        logging.error(
            f"Ошибка при обработке выбора услуги {service_id} или подготовке выбора сотрудника для пользователя {query.from_user.id}: {e}"
        )
        await query.answer(
            "Произошла ошибка при выборе услуги. Попробуйте позже.", show_alert=True
        )

    await query.answer()


@router.callback_query(
    BookingStates.waiting_for_employee, F.data.startswith("select_employee_")
)
async def process_employee_selection(query: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор сотрудника из inline клавиатуры."""
    employee_id_str = query.data.split("_")[2]

    try:
        employee_id = int(employee_id_str)
    except ValueError:
        logging.warning(
            f"Получен неверный ID сотрудника из callback: {query.data} для пользователя {query.from_user.id}"
        )
        await query.answer("Неверный формат ID сотрудника.", show_alert=True)
        return

    selected_employee = None
    try:
        async with async_session_factory() as session:
            employee_repo = EmployeeRepository(session)
            employee_service = EmployeeService(employee_repo)
            selected_employee = await employee_service.get_employee_by_id(employee_id)

        if selected_employee:
            await state.update_data(
                selected_employee_id=selected_employee.id,
                selected_employee_name=selected_employee.name,
                selected_employee_specialty=selected_employee.specialty,
            )
            data = await state.get_data()
            selected_service_name = data.get(
                "selected_service_name", "Услуга не выбрана"
            )
            await query.message.edit_text(
                f"Вы выбрали сотрудника: <b>{selected_employee.name}</b> ({selected_employee.specialty}).\n"
                f"Услуга: <b>{selected_service_name}</b>.\n\nТеперь выберите дату записи:",
                parse_mode="HTML",
            )
            year, month = date.today().year, date.today().month
            available_days = await get_available_days_for_employee(
                session, selected_employee.id, data["selected_service_id"], year, month
            )
            keyboard = create_calendar_keyboard(year, month, available_days)
            await query.message.answer(
                "Выберите дату записи:",
                reply_markup=keyboard,
            )
            await state.set_state(BookingStates.waiting_for_date)

        else:
            logging.warning(
                f"Пользователь {query.from_user.id} выбрал несуществующего сотрудника ID {employee_id}."
            )
            await query.answer(
                "Выбранный сотрудник не найден. Пожалуйста, выберите из списка.",
                show_alert=True,
            )

    except Exception as e:
        logging.error(
            f"Ошибка при обработке выбора сотрудника {employee_id} или подготовке выбора даты для пользователя {query.from_user.id}: {e}"
        )
        await query.answer(
            "Произошла ошибка при выборе сотрудника. Попробуйте позже.", show_alert=True
        )

    await query.answer()


@router.callback_query(
    BookingStates.waiting_for_employee, F.data == "back_to_service_selection"
)
async def back_to_service_selection_handler(query: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие кнопки "Назад к услугам" во время выбора сотрудника.
    Возвращает пользователя к выбору услуги.
    """
    logging.info(
        f"Пользователь {query.from_user.id} нажал 'Назад к услугам' из выбора сотрудника."
    )

    await state.update_data(
        selected_employee_id=None,
        selected_employee_name=None,
        selected_employee_specialty=None,
    )

    services = []
    try:
        async with async_session_factory() as session:
            service_repo = ServiceRepository(session)
            service_service = ServiceService(service_repo)
            services = await service_service.get_all_services()
    except Exception as e:
        logging.error(
            f"Ошибка при получении списка услуг для возврата к выбору услуги для пользователя {query.from_user.id}: {e}"
        )
        await query.answer(
            "Произошла ошибка при возврате к выбору услуги. Пожалуйста, начните заново /start.",
            show_alert=True,
        )
        await state.clear()
        return

    if not services:
        await query.answer(
            "Нет доступных услуг для выбора. Пожалуйста, начните заново /start.",
            show_alert=True,
        )
        await state.clear()
        return
    keyboard = create_service_selection_keyboard(services)

    await query.message.edit_text("Выберите услугу для записи:", reply_markup=keyboard)

    await state.set_state(BookingStates.waiting_for_service)
    await query.answer()


@router.callback_query(F.data.regexp(r"^calendar_(prev|next)_(\d{4})_(\d{1,2})$"))
async def handle_calendar_navigation(query: CallbackQuery, state: FSMContext):
    """Обработка навигации по календарю."""
    match = re.match(r"^calendar_(prev|next)_(\d{4})_(\d{1,2})$", query.data)
    direction, year, month = match.groups()
    year = int(year)
    month = int(month)

    # Получаем данные из state
    data = await state.get_data()
    employee_id = data["selected_employee_id"]
    service_id = data["selected_service_id"]

    try:
        async with async_session_factory() as session:
            available_dates = await get_available_days_for_employee(
                session, employee_id, service_id, year, month
            )

            keyboard = create_calendar_keyboard(year, month, available_dates)

            await query.message.edit_text(
                "Выберите дату для записи:", reply_markup=keyboard
            )

            await state.update_data(calendar_year=year, calendar_month=month)

    except Exception as e:
        logging.error(f"Ошибка при навигации по календарю: {e}")
        await query.answer("Произошла ошибка. Попробуйте еще раз.", show_alert=True)

    await query.answer()


@router.callback_query(BookingStates.waiting_for_time, F.data.startswith("time_"))
async def handle_time_selection(query: CallbackQuery, state: FSMContext):
    selected_time_str = query.data.replace("time_", "")
    data = await state.get_data()
    selected_date_str = data.get("selected_date")
    selected_service_id = data.get("selected_service_id")
    selected_employee_id = data.get("selected_employee_id")

    selected_datetime_obj = datetime.strptime(
        f"{selected_date_str} {selected_time_str}", "%d.%m.%Y %H:%M"
    )
    datetime_str = selected_datetime_obj.strftime("%d.%m.%Y %H:%M")
    if selected_datetime_obj < datetime.now():
        await query.answer(
            "Нельзя выбрать прошедшее время. Пожалуйста, выберите другое.",
            show_alert=True,
        )
        return

    try:
        async with async_session_factory() as session:
            service_repo = ServiceRepository(session)
            booking_repo = BookingRepository(session)
            user_repo = UserRepository(session)
            BookingService(booking_repo, user_repo, service_repo)

            duration = await service_repo.get_service_duration(selected_service_id)
            end_time = selected_datetime_obj + timedelta(minutes=duration)

            existing_bookings = await booking_repo.get_bookings_by_employee_and_date(
                employee_id=selected_employee_id, date=selected_datetime_obj.date()
            )
            slot_is_free = True
            for booking in existing_bookings:
                booking_end = booking.datetime + timedelta(
                    minutes=booking.service.duration
                )
                if not (
                    end_time <= booking.datetime or selected_datetime_obj >= booking_end
                ):
                    slot_is_free = False
                    break

            if not slot_is_free:
                await query.answer(
                    "Это время занято или пересекается с другой записью. Выберите другое.",
                    show_alert=True,
                )
                return

        await state.update_data(selected_time=selected_time_str)

    except Exception as e:
        logging.error(f"Ошибка при проверке времени записи: {e}")
        await query.answer(
            "Произошла ошибка при выборе времени. Попробуйте позже.", show_alert=True
        )
        return

    selected_service_name = data.get("selected_service_name")
    selected_employee_name = data.get("selected_employee_name")
    selected_employee_specialty = data.get("selected_employee_specialty")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить", callback_data="confirm_booking"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить", callback_data="cancel_fsm_process"
                )
            ],
        ]
    )
    await query.message.edit_text(
        f"Проверьте данные записи:\n\n"
        f"Услуга: <b>{selected_service_name}</b>\n"
        f"Сотрудник: <b>{selected_employee_name} ({selected_employee_specialty})</b>\n"
        f"Дата и время: <b>{datetime_str}</b>\n\n"
        f"Все верно?",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await state.set_state(BookingStates.waiting_for_confirmation)
    await query.answer()


@router.callback_query(
    BookingStates.waiting_for_time, F.data == "back_to_date_selection"
)
async def back_to_date_selection_handler(query: CallbackQuery, state: FSMContext):
    """Обработка возврата к выбору даты."""
    data = await state.get_data()
    year = data.get("calendar_year", date.today().year)
    month = data.get("calendar_month", date.today().month)
    employee_id = data["selected_employee_id"]
    service_id = data["selected_service_id"]

    try:
        async with async_session_factory() as session:
            available_dates = await get_available_days_for_employee(
                session, employee_id, service_id, year, month
            )

            keyboard = create_calendar_keyboard(year, month, available_dates)

            await query.message.edit_text(
                "Выберите дату для записи:", reply_markup=keyboard
            )

            await state.set_state(BookingStates.waiting_for_date)

    except Exception as e:
        logging.error(f"Ошибка при возврате к выбору даты: {e}")
        await query.answer("Произошла ошибка. Попробуйте еще раз.", show_alert=True)
        return

    await query.answer()


@router.callback_query(
    BookingStates.waiting_for_confirmation, F.data == "confirm_booking"
)
async def handle_booking_confirmation(query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_date_str = data.get("selected_date")
    selected_time_str = data.get("selected_time")
    selected_service_id = data.get("selected_service_id")
    selected_employee_id = data.get("selected_employee_id")
    user_telegram_id = query.from_user.id

    selected_datetime_obj = datetime.strptime(
        f"{selected_date_str} {selected_time_str}", "%d.%m.%Y %H:%M"
    )
    datetime_str = selected_datetime_obj.strftime("%d.%m.%Y %H:%M")

    try:
        async with async_session_factory() as session:
            service_repo = ServiceRepository(session)
            booking_repo = BookingRepository(session)
            user_repo = UserRepository(session)
            booking_service = BookingService(booking_repo, user_repo, service_repo)

            duration = await service_repo.get_service_duration(selected_service_id)
            end_time = selected_datetime_obj + timedelta(minutes=duration)

            existing_bookings = await booking_repo.get_bookings_by_employee_and_date(
                employee_id=selected_employee_id, date=selected_datetime_obj.date()
            )
            slot_is_free = True
            for booking in existing_bookings:
                booking_end = booking.datetime + timedelta(
                    minutes=booking.service.duration
                )
                if not (
                    end_time <= booking.datetime or selected_datetime_obj >= booking_end
                ):
                    slot_is_free = False
                    break

            if not slot_is_free:
                await query.answer(
                    "Это время занято или пересекается с другой записью. Выберите другое.",
                    show_alert=True,
                )
                return

            new_booking = await booking_service.create_booking(
                user_telegram_id=user_telegram_id,
                datetime_str=datetime_str,
                service_id=selected_service_id,
                employee_id=selected_employee_id,
            )

        if new_booking:
            await query.message.edit_text(
                f"✅ Ваша запись успешно создана!\n\n"
                f"Услуга: <b>{data.get('selected_service_name')}</b>\n"
                f"Сотрудник: <b>{data.get('selected_employee_name')} ({data.get('selected_employee_specialty')})</b>\n"
                f"Дата и время: <b>{new_booking.datetime.strftime('%d.%m.%Y %H:%M')}</b>\n"
                f"ID записи: <b>{new_booking.id}</b>\n\n"
                f"Мы ждем вас!",
                parse_mode="HTML",
            )
            await query.message.answer(
                "Вы в главном меню.", reply_markup=main_menu_kb()
            )
        else:
            await query.message.edit_text(
                "Не удалось создать запись. Произошла ошибка. Попробуйте еще раз.",
                reply_markup=main_menu_kb(),
            )

    except Exception as e:
        logging.error(
            f"Критическая ошибка при финализации записи для пользователя {query.from_user.id}: {e}"
        )
        await query.message.edit_text(
            "Произошла ошибка при обработке вашего запроса. Попробуйте позже.",
            reply_markup=main_menu_kb(),
        )
    finally:
        await state.clear()
        await query.answer()


@router.callback_query(F.data == "cancel_fsm_process")
async def cancel_fsm_process_callback_handler(query: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие inline кнопки 'Отменить запись' во время активного FSM процесса
    (выбора услуги, даты, времени), очищает состояние FSM.
    """
    logging.info(
        f"Пользователь {query.from_user.id} нажал inline кнопку 'Отменить запись' во время FSM процесса."
    )
    current_state = await state.get_state()  # Получаем текущее состояние

    if current_state is None:
        logging.warning(
            f"Пользователь {query.from_user.id} нажал FSM отмену, но состояние None."
        )
        await query.answer("Нет активной записи для отмены.", show_alert=True)
        return

    await state.clear()
    logging.info(
        f"Состояние FSM {current_state} очищено по нажатию inline кнопки отмены для пользователя {query.from_user.id}."
    )

    try:
        await query.message.edit_text("Действие отменено.", reply_markup=None)
    except Exception as e:
        logging.error(
            f"Ошибка при редактировании сообщения после отмены FSM inline кнопкой для пользователя {query.from_user.id}: {e}"
        )
        await query.message.answer("Действие отменено.")

    try:
        await query.message.answer("Вы в главном меню.", reply_markup=main_menu_kb())
    except Exception as e:
        logging.error(
            f"Ошибка при отправке главного меню после отмены FSM inline кнопкой для пользователя {query.from_user.id}: {e}"
        )
        await query.message.answer("Вы в главном меню.")

    await query.answer("Запись отменена.", show_alert=True)


@router.callback_query(F.data.startswith("cancel_booking_"))
async def process_cancel_booking_callback(query: CallbackQuery):
    booking_id_str = query.data.split("_")[-1]

    try:
        booking_id = int(booking_id_str)
        if booking_id <= 0:
            raise ValueError
    except ValueError:
        logging.warning(
            f"Получен неверный ID записи для отмены из callback: {query.data}"
        )
        await query.answer("Неверный формат ID записи.", show_alert=True)
        return

    user_telegram_id = query.from_user.id
    deleted = False

    try:
        async with async_session_factory() as session:
            booking_repo = BookingRepository(session)
            user_repo = UserRepository(session)
            service_repo = ServiceRepository(session)
            service = BookingService(booking_repo, user_repo, service_repo)

            deleted = await service.delete_user_booking(user_telegram_id, booking_id)

        if deleted:
            await query.answer("Запись успешно отменена!", show_alert=True)
            try:
                await query.message.answer(f"Запись с ID {booking_id} отменена.")
            except Exception as e:
                logging.error(f"Не удалось отправить сообщение после отмены: {e}")

        else:
            await query.answer(
                "Не удалось отменить запись. Возможно, она уже удалена или не принадлежит вам.",
                show_alert=True,
            )
            logging.warning(
                f"Неудачная попытка отмены записи {booking_id} пользователем {user_telegram_id} (не найдена/не владелец)."
            )

    except Exception as e:
        logging.error(
            f"Ошибка при обработке отмены записи {booking_id} пользователем {user_telegram_id}: {e}"
        )
        await query.answer(
            "Произошла ошибка при отмене записи. Попробуйте позже.", show_alert=True
        )


@router.message(BookingStates.waiting_for_date)
async def handle_unexpected_message_in_date_state(message: Message, state: FSMContext):
    await message.answer(
        "Пожалуйста, выберите дату через календарь ниже 👇.\n"
        "Если вы хотите отменить запись — нажмите кнопку 'Отменить'."
    )


@router.message(BookingStates.waiting_for_time)
async def handle_unexpected_message_in_time_state(message: Message, state: FSMContext):
    await message.answer(
        "Пожалуйста, выберите время из предложенных вариантов ниже 👇.\n"
        "Если вы хотите отменить запись — нажмите кнопку 'Отменить'."
    )


@router.callback_query(F.data.startswith("booking_details_"))
async def show_booking_details_callback(query: CallbackQuery):
    booking_id_str = query.data.split("_")[-1]
    try:
        booking_id = int(booking_id_str)
    except ValueError:
        await query.answer("Некорректный ID записи.", show_alert=True)
        return

    user_telegram_id = query.from_user.id

    try:
        async with async_session_factory() as session:
            booking_repo = BookingRepository(session)
            UserRepository(session)
            service_repo = ServiceRepository(session)
            employee_repo = EmployeeRepository(session)
            booking = await booking_repo.get_booking_by_id(booking_id)
            if not booking or booking.user_telegram_id != user_telegram_id:
                await query.answer(
                    "Запись не найдена или не принадлежит вам.", show_alert=True
                )
                return

            service = await service_repo.get_service_by_id(booking.service_id)
            employee = await employee_repo.get_employee_by_id(booking.employee_id)

        details = (
            f"🗓 <b>Детали записи №{booking.id}</b>\n\n"
            f"<b>Услуга:</b> {service.name if service else '—'}\n"
            f"<b>Сотрудник:</b> {employee.name if employee else '—'}\n"
            f"<b>Дата и время:</b> {booking.datetime.strftime('%d.%m.%Y %H:%M')}\n"
            f"<b>Телефон:</b> {booking.phone}\n"
            f"<b>Создана:</b> {booking.created_at.strftime('%d.%m.%Y %H:%M') if booking.created_at else '—'}"
        )
        await query.message.answer(details, parse_mode="HTML")
        await query.answer()
    except Exception as e:
        logging.error(f"Ошибка при получении подробностей записи {booking_id}: {e}")
        await query.answer("Ошибка при получении информации.", show_alert=True)


@router.message(Command("admin"))
@router.message(F.text == "💬 Чат с администратором")
async def start_admin_chat(message: Message, state: FSMContext):
    """Начало чата с администратором"""
    await message.answer(
        "👋 Вы в чате с администратором. Отправьте ваше сообщение или фото.\n"
        "Администратор ответит вам в ближайшее время.\n"
        "Для выхода из чата используйте команду /cancel",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Выйти из чата", callback_data="exit_chat"
                    )
                ]
            ]
        ),
    )
    await state.set_state(ChatStates.in_chat)


@router.message(ChatStates.in_chat, F.content_type.in_({"text", "photo"}))
async def handle_user_message(message: Message, state: FSMContext):
    """Обработка сообщений пользователя в чате"""
    user_id = message.from_user.id

    try:
        async with async_session_factory() as session:
            message_repo = MessageRepository(session)

            if message.content_type == "text":
                await message_repo.create_message(
                    user_telegram_id=user_id, message_text=message.text
                )
                await message.answer("✅ Ваше сообщение отправлено администратору")

            elif message.content_type == "photo":
                photo_file_id = message.photo[-1].file_id
                caption = message.caption or "Фото без описания"

                await message_repo.create_message(
                    user_telegram_id=user_id,
                    message_text=caption,
                    attachment_id=photo_file_id,
                )
                await message.answer("✅ Ваше фото отправлено администратору")

            for admin_id in config.ADMIN_IDS:
                try:
                    await message.bot.send_message(
                        admin_id,
                        f"📨 Новое сообщение от пользователя {user_id}:\n"
                        f"{message.text if message.content_type == 'text' else caption}",
                    )
                    if message.content_type == "photo":
                        await message.bot.send_photo(
                            admin_id, photo_file_id, caption=caption
                        )
                except Exception as e:
                    logging.error(
                        f"Не удалось отправить уведомление админу {admin_id}: {e}"
                    )

    except Exception as e:
        logging.error(f"Ошибка при обработке сообщения от пользователя {user_id}: {e}")
        await message.answer(
            "❌ Произошла ошибка при отправке сообщения. Попробуйте позже."
        )


@router.callback_query(F.data == "exit_chat")
async def exit_admin_chat(query: CallbackQuery, state: FSMContext):
    """Выход из чата с администратором"""
    await state.clear()
    await query.message.edit_text("Вы вышли из чата с администратором.")
    await query.message.answer("Вы в главном меню", reply_markup=main_menu_kb())


@router.message(F.text == "💎 Моя лояльность")
async def show_loyalty_status(message: Message):
    """Показывает статус в программе лояльности"""
    try:
        async with async_session_factory() as session:
            loyalty_repo = LoyaltyRepository(session)
            loyalty_service = LoyaltyService(loyalty_repo)

            status_message = await loyalty_service.get_user_status(message.from_user.id)
            await message.answer(status_message)

    except Exception as e:
        logging.error(f"Ошибка при получении статуса лояльности: {e}")
        await message.answer("Не удалось получить информацию о программе лояльности")
