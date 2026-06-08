import logging
from config import Config

from aiogram import Router, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from sqlalchemy import select, and_

from db.database import async_session_factory

from repositories.message_repo import MessageRepository
from repositories.service_repo import ServiceRepository
from repositories.booking_repo import BookingRepository
from repositories.user_repo import UserRepository
from repositories.employee_repo import EmployeeRepository

from services.booking_service import BookingService
from services.service_service import ServiceService
from services.employee_service import EmployeeService

from keyboards.keyboards import (
    create_admin_service_management_keyboard,
    create_admin_employee_association_keyboard,
    create_employee_service_toggle_keyboard,
    create_admin_employee_management_keyboard,
    main_menu_kb,
)

from models.models import (
    Employee,
    AdminServiceStates,
    AdminEmployeeStates,
    employee_service_association,
    EmployeeSchedule,
    Contacts,
    ChatStates,
)

from datetime import datetime

router = Router()

config = Config.load()


@router.message(Command("admin"))
async def admin_panel(message: Message):
    await message.answer(
        "Добро пожаловать в админ-панель:\n"
        "/list — показать все записи\n"
        "/delete ID — удалить запись (например: `/delete 1`)\n"
        "/admin_help — показать список админских команд\n"
    )


@router.message(Command("list"))
async def list_bookings(message: Message):
    try:
        async with async_session_factory() as session:
            booking_repo = BookingRepository(session)
            user_repo = UserRepository(session)
            service_repo = ServiceRepository(session)
            service = BookingService(booking_repo, user_repo, service_repo)
            bookings = await service.list_bookings()

        if not bookings:
            await message.answer("Нет активных записей.")
            return

        response = "📋 Список записей:\n\n"
        for b in bookings:
            response += f"<b>ID:</b> {b.id}\n"
            if b.user_telegram_id:
                response += (
                    f"  <b>Пользователь (Telegram ID):</b> {b.user_telegram_id}\n"
                )
            response += f"  <b>Имя:</b> {b.name}\n"
            response += f"  <b>Телефон:</b> {b.phone}\n"
            response += f"  <b>Дата:</b> {b.datetime}\n"
            response += "-" * 15 + "\n"

        if len(response) > 4096:
            response = (
                response[:4000]
                + "\n...\nСлишком много записей для одного сообщения. Показаны первые."
            )
        await message.answer(response, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Ошибка при получении списка бронирований: {e}")
        await message.answer("Произошла ошибка при получении списка записей.")


@router.message(Command("admin_help"))
async def admin_help_cmd(message: Message):
    """
    Админская команда для отображения списка админских команд.
    Предназначена только для администраторов.
    """
    if not message.from_user:
        return
    admin_user_id = message.from_user.id
    logging.info(f"Админ {admin_user_id} запросил помощь по админским командам.")

    admin_commands_list = (
        "<b>👨‍💻 Админские команды:</b>\n\n"
        "<code>/admin_bookings</code> - Показать все активные записи\n"
        "<code>/admin_edit_contacts</code> - Изменить контактную информацию\n"
        "<code>/admin_services</code> - Управление услугами (добавить, изменить, удалить)\n"
        "<code>/admin_add_service</code> - Быстро добавить новую услугу\n"
        "<code>/admin_employees</code> - Управление сотрудниками (список, изменить, удалить)\n"
        "<code>/admin_add_employee</code> - Быстро добавить нового сотрудника\n"
        "<code>/admin_manage_employee_services</code> - Управление услугами, которые оказывает сотрудник\n"
        "<code>/admin_cancel &lt;ID&gt;</code> - Отменить запись по ID\n"
        "<code>/admin_edit_schedule</code> - Редактировать график сотрудника\n"
        "<code>/admin_help</code> - Показать этот список команд\n\n"
        "<code>/admin_exit</code> - Выйти из админ-меню и вернуться к пользовательскому меню\n\n"
        "В большинстве FSM режимов админки для отмены используйте команду <code>/cancel</code>."
    )

    await message.answer(admin_commands_list, parse_mode="HTML")


@router.message(
    Command("admin_cancel"),
    F.text.contains(" "),
    ~StateFilter(AdminServiceStates, AdminEmployeeStates),
)
async def admin_cancel_booking_by_id(
    message: Message, command: CommandObject, state: FSMContext
):
    """
    Админская команда для отмены записи по ее ID.
    Принимает ID записи как аргумент команды /admin_cancel <ID>.
    Отменяет запись в БД и отправляет уведомление пользователю.
    """
    admin_user_id = message.from_user.id
    logging.info(f"Админ {admin_user_id} попытался отменить запись по ID.")

    booking_id_str = command.args

    if not booking_id_str:
        await message.answer(
            "ℹ️ Используйте команду `/admin_cancel <ID записи>`, чтобы отменить запись.",
            parse_mode="Markdown",
        )
        return

    try:
        booking_id = int(booking_id_str)
        if booking_id <= 0:
            raise ValueError("ID записи должен быть положительным числом.")
    except ValueError:
        await message.answer(
            "❌ Неверный формат ID записи. ID должен быть числом.",
            parse_mode="Markdown",
        )
        logging.warning(
            f"Админ {admin_user_id} ввел неверный формат ID записи '{booking_id_str}' для отмены."
        )
        return

    logging.info(f"Админ {admin_user_id} запросил отмену записи ID={booking_id}.")

    booking_to_cancel = None
    deleted = False

    try:
        async with async_session_factory() as session:
            booking_repo = BookingRepository(session)
            user_repo = UserRepository(session)
            service_repo = ServiceRepository(session)
            booking_service = BookingService(booking_repo, user_repo, service_repo)

            booking_to_cancel = await booking_service.get_booking_by_id(booking_id)

            if not booking_to_cancel:
                await message.answer(
                    f"❌ Запись с ID=`{booking_id}` не найдена.", parse_mode="Markdown"
                )
                logging.warning(
                    f"Админ {admin_user_id} попытался отменить несуществующую запись ID={booking_id}."
                )
                return

            if booking_to_cancel.datetime <= datetime.now():
                await message.answer(
                    f"❌ Запись с ID=`{booking_id}` уже прошла. Нельзя отменить прошедшую запись.",
                    parse_mode="Markdown",
                )
                logging.warning(
                    f"Админ {admin_user_id} попытался отменить прошедшую запись ID={booking_id}."
                )
                return

            deleted = await booking_service.delete_booking(booking_id)

            if deleted:
                logging.info(
                    f"Запись ID={booking_id} успешно отменена админом {admin_user_id}."
                )
                await message.answer(
                    f"✅ Запись с ID=`{booking_id}` успешно отменена.",
                    parse_mode="Markdown",
                )

                user_to_notify = booking_to_cancel.user
                if user_to_notify and user_to_notify.telegram_id:
                    try:
                        service_name = booking_to_cancel.service.name
                        employee_name = booking_to_cancel.employee.name
                        booking_time_str = booking_to_cancel.datetime.strftime(
                            "%d.%m.%Y в %H:%M"
                        )

                        notification_message = (
                            f"🤖 Уважаемый(ая) **{user_to_notify.name}**!\n\n"
                            f"Ваша запись на услугу **'{service_name}'** "
                            f"у сотрудника **'{employee_name}'** "
                            f"на **{booking_time_str}** "
                            f"была отменена администратором.\n\n"
                            f"Приносим извинения за возможные неудобства."
                        )
                        await message.bot.send_message(
                            chat_id=user_to_notify.telegram_id,
                            text=notification_message,
                            parse_mode="Markdown",
                        )
                        logging.info(
                            f"Пользователь {user_to_notify.telegram_id} успешно уведомлен об отмене записи ID={booking_id}."
                        )
                    except TelegramForbiddenError:
                        logging.warning(
                            f"Не удалось уведомить пользователя {user_to_notify.telegram_id} об отмене записи ID={booking_id}: Бот заблокирован пользователем."
                        )
                        await message.answer(
                            f"⚠️ Не удалось уведомить пользователя `{user_to_notify.telegram_id}` об отмене записи (бот заблокирован).",
                            parse_mode="Markdown",
                        )
                    except TelegramBadRequest as e:
                        logging.error(
                            f"Ошибка Telegram API при отправке уведомления пользователю {user_to_notify.telegram_id} об отмене записи ID={booking_id}: {e}"
                        )
                        await message.answer(
                            f"❗ Произошла ошибка при отправке уведомления пользователю `{user_to_notify.telegram_id}` об отмене.",
                            parse_mode="Markdown",
                        )
                    except Exception as notify_e:
                        logging.error(
                            f"Неожиданная ошибка при уведомлении пользователя {user_to_notify.telegram_id} об отмене записи ID={booking_id}: {notify_e}"
                        )
                        await message.answer(
                            f"❗ Произошла неожиданная ошибка при отправке уведомления пользователю `{user_to_notify.telegram_id}`.",
                            parse_mode="Markdown",
                        )

                else:
                    logging.warning(
                        f"Не удалось уведомить пользователя об отмене записи ID={booking_id}: Нет связанного пользователя или telegram_user_id."
                    )
                    await message.answer(
                        f"⚠️ Не удалось уведовить пользователя об отмене записи с ID=`{booking_id}` (нет данных пользователя).",
                        parse_mode="Markdown",
                    )

            else:
                logging.warning(
                    f"Не удалось отменить запись ID={booking_id} (delete_booking вернул False) для админа {admin_user_id}. Запись могла быть уже удалена."
                )
                await message.answer(
                    f"❌ Не удалось отменить запись с ID=`{booking_id}`. Запись не найдена или произошла ошибка при удалении.",
                    parse_mode="Markdown",
                )

    except Exception as e:
        logging.error(
            f"Критическая ошибка при отмене записи ID={booking_id} админом {admin_user_id}: {e}"
        )
        await message.answer(
            "Произошла ошибка при отмене записи. Пожалуйста, попробуйте позже.",
            parse_mode="Markdown",
        )


@router.message(Command("admin_bookings"))
async def admin_list_bookings_cmd(message: Message):
    """
    Админская команда для просмотра всех записей в базе данных.
    Срабатывает только для пользователей из списка ADMIN_IDS.
    """
    logging.info(f"Админ {message.from_user.id} запросил список всех записей.")

    bookings = []
    try:
        async with async_session_factory() as session:
            booking_repo = BookingRepository(session)
            user_repo = UserRepository(session)
            service_repo = ServiceRepository(session)
            booking_service = BookingService(booking_repo, user_repo, service_repo)
            bookings = await booking_service.list_all_bookings()

    except Exception as e:
        logging.error(
            f"Ошибка при получении списка всех записей для админа {message.from_user.id}: {e}"
        )
        await message.answer("Произошла ошибка при загрузке списка записей.")
        return

    if not bookings:
        await message.answer("В базе данных пока нет записей.")
        return

    response_text = "📚 **Все записи:**\n\n"

    for booking in bookings:
        service_name = booking.service.name if booking.service else "Не указана"
        employee_info = "Не выбран"
        if booking.employee:
            employee_info = booking.employee.name
            if booking.employee.specialty:
                employee_info += f" ({booking.employee.specialty})"

        booking_datetime_str = "Неверный формат даты"
        if isinstance(booking.datetime, datetime):
            booking_datetime_str = booking.datetime.strftime("%d.%m.%Y %H:%M")
        else:
            # Логгируем, если datetime не datetime объект (после исправления БД такого быть не должно)
            logging.warning(
                f"Поле 'datetime' для записи ID={booking.id} не является datetime объектом: {type(booking.datetime)}"
            )
            booking_datetime_str = str(
                booking.datetime
            )  # Преобразуем в строку на всякий случай

        # Форматируем время создания записи (created_at)
        created_at_str = "Неверный формат даты"
        if booking.created_at and isinstance(
            booking.created_at, datetime
        ):  # created_at может быть None
            created_at_str = booking.created_at.strftime("%d.%m.%Y %H:%M")
        elif booking.created_at:
            logging.warning(
                f"Поле 'created_at' для записи ID={booking.id} не является datetime объектом: {type(booking.created_at)}"
            )
            created_at_str = str(booking.created_at)
        else:
            created_at_str = "Не указано"  # Если created_at равно None

        response_text += (
            f"**ID:** {booking.id}\n"  # Жирный шрифт для ID
            f"**Пользователь:** {booking.name} (`{booking.user_telegram_id}`)\n"  # Имя и ID пользователя, ID моноширинным шрифтом
            f"**Телефон:** {booking.phone}\n"
            f"**Дата/Время:** {booking_datetime_str}\n"
            f"**Услуга:** {service_name}\n"
            f"**Сотрудник:** {employee_info}\n"
            f"**Создана:** {created_at_str}\n"
            f"---\n"  # Разделитель между записями
        )

    if len(response_text) > 4000:
        await message.answer(
            response_text[:4000]
            + "\n...\n(Список слишком длинный, показана часть. Для полного списка используйте другой способ или фильтры.)"
        )
    else:
        await message.answer(response_text, parse_mode="Markdown")


@router.message(Command("admin_add_service"), ~StateFilter(AdminServiceStates))
async def admin_add_service_cmd(message: Message, state: FSMContext):
    """
    Админская команда для начала добавления новой услуги.
    Переводит админа в состояние ожидания названия услуги.
    """
    admin_user_id = message.from_user.id
    logging.info(f"Админ {admin_user_id} начал процесс добавления услуги.")

    await state.clear()

    await state.set_state(AdminServiceStates.waiting_for_service_name)

    await message.answer(
        "✍️ **Добавление новой услуги.**\n\nВведите название услуги:",
        parse_mode="Markdown",
    )


@router.message(AdminServiceStates.waiting_for_service_name, F.text)
async def process_admin_service_name(message: Message, state: FSMContext):
    """
    Обрабатывает ввод названия услуги админом в состоянии AdminServiceStates.waiting_for_service_name.
    Сохраняет название в FSM контекст и переходит в состояние ожидания цены.
    """
    admin_user_id = message.from_user.id
    service_name = message.text.strip()

    logging.info(f"Админ {admin_user_id} ввел название услуги: '{service_name}'.")

    if not service_name:
        await message.answer(
            "Название услуги не может быть пустым. Пожалуйста, введите название услуги:"
        )
        return

    await state.update_data(new_service_name=service_name)
    logging.info(
        f"Название услуги '{service_name}' сохранено в FSM для админа {admin_user_id}."
    )

    await state.set_state(AdminServiceStates.waiting_for_service_price)

    await message.answer(
        "💰 **Добавление услуги.**\n\nТеперь введите цену услуги (например, '1500 руб' или 'Договорная').\n\nЕсли цена не нужна, просто отправьте символ `-` (тире).",
        parse_mode="Markdown",
    )


@router.message(AdminServiceStates.waiting_for_service_price, F.text)
async def process_admin_service_price(message: Message, state: FSMContext):
    """
    Обрабатывает ввод цены услуги админом в состоянии AdminServiceStates.waiting_for_service_price.
    Сохраняет цену (или None) в FSM контекст и переходит в состояние ожидания описания.
    """
    admin_user_id = message.from_user.id
    service_price_input = message.text.strip()

    logging.info(f"Админ {admin_user_id} ввел цену услуги: '{service_price_input}'.")

    service_price = None

    if service_price_input == "-":
        logging.info(f"Админ {admin_user_id} пропустил ввод цены услуги.")
    else:
        service_price = service_price_input

    await state.update_data(new_service_price=service_price)
    logging.info(
        f"Цена услуги '{service_price}' сохранена в FSM для админа {admin_user_id}."
    )

    await state.set_state(AdminServiceStates.waiting_for_service_description)

    await message.answer(
        "📝 **Добавление новой услуги.**\n\nТеперь введите описание услуги (можно пропустить, написав '-'):",
        parse_mode="Markdown",
    )


@router.message(AdminServiceStates.waiting_for_service_description, F.text)
async def process_admin_service_description(message: Message, state: FSMContext):
    """
    Обрабатывает ввод описания услуги админом в состоянии AdminServiceStates.waiting_for_service_description.
    Сохраняет описание (или None), собирает все данные из FSM и создает услугу в БД.
    """
    admin_user_id = message.from_user.id
    service_description_input = message.text.strip()

    logging.info(
        f"Админ {admin_user_id} ввел описание услуги: '{service_description_input}'."
    )

    service_description = None

    if service_description_input == "-":
        logging.info(f"Админ {admin_user_id} пропустил ввод описания услуги.")
    else:
        service_description = service_description_input

    await state.update_data(new_service_description=service_description)
    logging.info(
        f"Описание услуги '{service_description}' сохранено в FSM для админа {admin_user_id}."
    )
    await state.set_state(AdminServiceStates.waiting_for_service_duration)
    await message.answer("⏱ Введите длительность услуги в минутах (например, 60):")


@router.message(AdminServiceStates.waiting_for_service_duration, F.text)
async def process_admin_service_duration(message: Message, state: FSMContext):
    duration_text = message.text.strip()

    try:
        duration = int(duration_text)
        if duration <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Пожалуйста, введите положительное целое число (минуты).")
        return

    service_data = await state.get_data()
    editing_service_id = service_data.get("editing_service_id")
    new_service_name = service_data.get("new_service_name")
    new_service_price = service_data.get("new_service_price")
    new_service_description = service_data.get("new_service_description")

    try:
        async with async_session_factory() as session:
            service_repo = ServiceRepository(session)
            service_service = ServiceService(service_repo)

            if editing_service_id:
                updates = {"duration": duration}
                updated = await service_service.update_service(
                    editing_service_id, updates
                )
                if updated:
                    await message.answer(
                        f"✅ Длительность услуги ID=`{editing_service_id}` успешно обновлена на: **{duration} мин**",
                        parse_mode="Markdown",
                    )
                else:
                    await message.answer(
                        f"❌ Не удалось обновить длительность услуги ID=`{editing_service_id}`. Возможно, услуга не найдена.",
                        parse_mode="Markdown",
                    )
            else:
                if not new_service_name:
                    await message.answer(
                        "Название услуги не указано. Добавление невозможно."
                    )
                    await state.clear()
                    return

                added_service = await service_service.add_service(
                    name=new_service_name,
                    price=new_service_price,
                    description=new_service_description,
                    duration=duration,
                )
                if added_service:
                    await message.answer(
                        f"✅ Новая услуга успешно добавлена!\n\n"
                        f"**Название:** {added_service.name}\n"
                        f"**Цена:** {added_service.price if added_service.price else 'Не указано'}\n"
                        f"**Описание:** {added_service.description if added_service.description else 'Не указано'}\n"
                        f"**Длительность:** {added_service.duration} минут",
                        parse_mode="Markdown",
                    )
                else:
                    await message.answer(
                        f"❌ Не удалось добавить услугу '{new_service_name}'. Возможно, услуга с таким названием уже существует."
                    )
    except Exception as e:
        logging.error(f"Ошибка при сохранении/редактировании услуги: {e}")
        await message.answer(
            "Произошла ошибка при сохранении услуги. Попробуйте еще раз."
        )
    finally:
        await state.clear()


@router.message(Command("admin_services"), ~StateFilter(AdminServiceStates))
async def admin_list_services_cmd(message: Message, state: FSMContext):
    """
    Админская команда для просмотра списка услуг с кнопками для редактирования/удаления.
    """
    admin_user_id = message.from_user.id
    logging.info(f"Админ {admin_user_id} запросил список услуг для управления.")

    services = []
    try:
        async with async_session_factory() as session:
            service_repo = ServiceRepository(session)
            service_service = ServiceService(service_repo)

            services = await service_service.get_all_services()

    except Exception as e:
        logging.error(
            f"Ошибка при получении списка услуг для админа {admin_user_id}: {e}"
        )
        await message.answer(
            "Произошла ошибка при загрузке списка услуг для управления."
        )
        return

    if not services:
        await message.answer("В базе данных пока нет услуг для управления.")
        # Возможно, предложить добавить услугу?
        await message.answer(
            "Вы можете добавить новую услугу командой /admin_add_service"
        )  # Предлагаем добавить
        return  # Прерываем выполнение

    management_keyboard = create_admin_service_management_keyboard(services)

    if management_keyboard:
        await message.answer(
            "📋 **Управление услугами:**\n\nВыберите услугу для редактирования или удаления:",
            parse_mode="Markdown",
            reply_markup=management_keyboard,
        )
        await state.set_state(AdminServiceStates.waiting_for_service_management_choice)
        logging.info(
            f"Админ {admin_user_id} переведен в состояние {AdminServiceStates.waiting_for_service_management_choice}."
        )


@router.callback_query(
    AdminServiceStates.waiting_for_service_management_choice,
    F.data.startswith("admin_edit_service_"),
)
async def admin_select_service_to_edit(query: CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор услуги для редактирования из списка управления услугами.
    Извлекает ID услуги, сохраняет его и предлагает выбрать поле для редактирования.
    """
    admin_user_id = query.from_user.id
    service_id_str = query.data.split("_")[3]

    try:
        service_id = int(service_id_str)
        if service_id <= 0:
            raise ValueError("ID услуги должен быть положительным числом.")
    except ValueError as e:
        logging.warning(
            f"Админ {admin_user_id} получил неверный ID услуги из callback для редактирования: '{query.data}'. Ошибка: {e}"
        )
        await query.answer("Неверный формат ID услуги.", show_alert=True)
        return

    logging.info(
        f"Админ {admin_user_id} выбрал услугу ID={service_id} для редактирования."
    )

    service_to_edit = None  # Инициализируем
    try:
        async with async_session_factory() as session:
            service_repo = ServiceRepository(session)
            service_service = ServiceService(service_repo)
            service_to_edit = await service_service.get_service_by_id(service_id)

        if not service_to_edit:
            logging.warning(
                f"Админ {admin_user_id} попытался отредактировать несуществующую услугу ID={service_id}."
            )
            await query.answer("Услуга не найдена.", show_alert=True)
            return

    except Exception as e:
        logging.error(
            f"Ошибка при проверке услуги ID={service_id} для редактирования админом {admin_user_id}: {e}"
        )
        await query.answer(
            "Произошла ошибка при подготовке к редактированию.", show_alert=True
        )
        return

    await state.update_data(editing_service_id=service_id)  # <-- Сохраняем ID
    logging.info(
        f"ID редактируемой услуги {service_id} сохранен в FSM для админа {admin_user_id}."
    )

    edit_field_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Название", callback_data="admin_edit_field_name"
                )
            ],
            [InlineKeyboardButton(text="Цена", callback_data="admin_edit_field_price")],
            [
                InlineKeyboardButton(
                    text="Описание", callback_data="admin_edit_field_description"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Длительность", callback_data="admin_edit_field_duration"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Отмена редактирования",
                    callback_data="admin_cancel_edit_service",
                )
            ],
        ]
    )

    await query.message.edit_text(
        f"✏️ **Редактирование услуги:**\n\n"
        f"**Название:** {service_to_edit.name}\n"
        f"**Цена:** {service_to_edit.price if service_to_edit.price else 'Не указано'}\n"
        f"**Описание:** {service_to_edit.description if service_to_edit.description else 'Не указано'}\n\n"
        f"Выберите, что хотите изменить:",
        parse_mode="Markdown",
        reply_markup=edit_field_keyboard,
    )

    await state.set_state(AdminServiceStates.waiting_for_edit_choice)
    logging.info(
        f"Админ {admin_user_id} переведен в состояние {AdminServiceStates.waiting_for_edit_choice}."
    )

    await query.answer("Выберите поле для редактирования.", show_alert=False)


@router.callback_query(
    AdminServiceStates.waiting_for_service_management_choice,
    F.data.startswith("admin_delete_service_"),
)
async def admin_select_service_to_delete(query: CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор услуги для удаления из списка управления услугами.
    Извлекает ID услуги, сохраняет его и запрашивает подтверждение удаления.
    """
    admin_user_id = query.from_user.id
    service_id_str = query.data.split("_")[3]

    try:
        service_id = int(service_id_str)
        if service_id <= 0:
            raise ValueError("ID услуги должен быть положительным числом.")
    except ValueError as e:
        logging.warning(
            f"Админ {admin_user_id} получил неверный ID услуги из callback для удаления: '{query.data}'. Ошибка: {e}"
        )
        await query.answer("Неверный формат ID услуги.", show_alert=True)
        return

    logging.info(f"Админ {admin_user_id} выбрал услугу ID={service_id} для удаления.")

    service_to_delete = None
    try:
        async with async_session_factory() as session:
            service_repo = ServiceRepository(session)
            service_service = ServiceService(service_repo)
            service_to_delete = await service_service.get_service_by_id(service_id)

        if not service_to_delete:
            logging.warning(
                f"Админ {admin_user_id} попытался удалить несуществующую услугу ID={service_id}."
            )
            await query.answer("Услуга не найдена.", show_alert=True)
            return

    except Exception as e:
        logging.error(
            f"Ошибка при проверке услуги ID={service_id} для удаления админом {admin_user_id}: {e}"
        )
        await query.answer(
            "Произошла ошибка при подготовке к удалению.", show_alert=True
        )
        return

    await state.update_data(deleting_service_id=service_id)
    logging.info(
        f"ID удаляемой услуги {service_id} сохранен в FSM для админа {admin_user_id}."
    )

    confirm_delete_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"✅ Да, удалить услугу '{service_to_delete.name}'",
                    callback_data="admin_confirm_delete_service",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Нет, отмена", callback_data="admin_cancel_delete_service"
                )
            ],
        ]
    )

    await query.message.edit_text(
        f"🗑️ **Удаление услуги:**\n\n"
        f"Вы собираетесь удалить услугу:\n"
        f"**Название:** {service_to_delete.name}\n"
        f"**Цена:** {service_to_delete.price if service_to_delete.price else 'Не указано'}\n"
        f"**Описание:** {service_to_delete.description if service_to_delete.description else 'Не указано'}\n\n"
        f"**Вы уверены?** Это действие нельзя отменить.",
        parse_mode="Markdown",
        reply_markup=confirm_delete_keyboard,
    )

    await state.set_state(AdminServiceStates.confirm_delete_service)
    logging.info(
        f"Админ {admin_user_id} переведен в состояние {AdminServiceStates.confirm_delete_service}."
    )

    await query.answer("Ожидаю подтверждение удаления.", show_alert=False)


@router.callback_query(
    AdminServiceStates.confirm_delete_service, F.data == "admin_confirm_delete_service"
)
async def admin_confirm_delete_service(query: CallbackQuery, state: FSMContext):
    """
    Обрабатывает подтверждение удаления услуги админом.
    Удаляет услугу из базы данных и сообщает результат.
    """
    admin_user_id = query.from_user.id
    logging.info(f"Админ {admin_user_id} подтвердил удаление услуги.")

    data = await state.get_data()
    service_id_to_delete = data.get("deleting_service_id")

    if service_id_to_delete is None:
        logging.error(
            f"Ошибка FSM: ID услуги для удаления не найден в контексте для админа {admin_user_id} в состоянии confirm_delete_service."
        )
        await query.answer(
            "Произошла ошибка при удалении услуги. ID услуги не найден.",
            show_alert=True,
        )
        await state.clear()
        await query.message.edit_text(
            "Процесс удаления прерван из-за ошибки.", reply_markup=None
        )
        return

    deleted = False
    try:
        async with async_session_factory() as session:
            service_repo = ServiceRepository(session)
            service_service = ServiceService(service_repo)
            deleted = await service_service.delete_service(service_id_to_delete)

        if deleted:
            logging.info(
                f"Услуга ID={service_id_to_delete} успешно удалена из БД админом {admin_user_id}."
            )
            await query.message.edit_text(
                f"✅ Услуга ID=`{service_id_to_delete}` успешно удалена.",
                parse_mode="Markdown",
            )
        else:
            logging.warning(
                f"Попытка удаления услуги ID={service_id_to_delete}, но услуга не найдена в БД при вызове delete_service (админ {admin_user_id})."
            )
            await query.message.edit_text(
                f"❌ Услуга ID=`{service_id_to_delete}` не найдена или уже удалена.",
                parse_mode="Markdown",
            )

    except Exception as e:
        logging.error(
            f"Критическая ошибка при удалении услуги ID={service_id_to_delete} админом {admin_user_id}: {e}"
        )
        await query.message.edit_text(
            "Произошла ошибка при удалении услуги. Пожалуйста, попробуйте позже."
        )
    finally:
        await state.clear()
        logging.info(
            f"Состояние FSM удаления услуги очищено для админа {admin_user_id} после подтверждения."
        )

    await query.answer("Услуга удалена.", show_alert=False)


@router.callback_query(
    AdminServiceStates.confirm_delete_service, F.data == "admin_cancel_delete_service"
)
async def admin_cancel_delete_service(query: CallbackQuery, state: FSMContext):
    """
    Обрабатывает отмену удаления услуги админом в состоянии подтверждения удаления.
    Очищает состояние FSM и сообщает об отмене.
    """
    admin_user_id = query.from_user.id
    logging.info(f"Админ {admin_user_id} отменил удаление услуги.")

    await state.clear()
    logging.info(
        f"Состояние FSM удаления услуги очищено после отмены для админа {admin_user_id}."
    )

    await query.message.edit_text("Отмена удаления услуги.", reply_markup=None)

    await query.answer("Удаление отменено.", show_alert=False)


@router.callback_query(
    AdminServiceStates.waiting_for_edit_choice, F.data == "admin_cancel_edit_service"
)
async def admin_cancel_edit_service(query: CallbackQuery, state: FSMContext):
    """
    Обрабатывает отмену редактирования услуги админом из состояния выбора поля.
    Очищает состояние FSM и сообщает об отмене.
    """
    admin_user_id = query.from_user.id  # Получаем ID админа
    logging.info(
        f"Админ {admin_user_id} отменил редактирование услуги из состояния выбора поля."
    )

    await state.clear()
    logging.info(
        f"Состояние FSM редактирования услуги очищено после отмены для админа {admin_user_id}."
    )

    await query.message.edit_text("Отмена редактирования услуги.", reply_markup=None)

    await query.answer("Редактирование отменено.", show_alert=False)


@router.callback_query(
    AdminServiceStates.waiting_for_edit_choice, F.data.startswith("admin_edit_field_")
)
async def admin_choose_service_field_to_edit(query: CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор поля услуги для редактирования админом.
    Переводит в соответствующее состояние ожидания нового значения и запрашивает его.
    """
    admin_user_id = query.from_user.id
    field_name = query.data.split("_")[3]

    logging.info(
        f"Админ {admin_user_id} выбрал поле '{field_name}' для редактирования услуги."
    )

    data = await state.get_data()
    editing_service_id = data.get("editing_service_id")

    if editing_service_id is None:
        logging.error(
            f"Ошибка FSM: ID услуги для редактирования не найден в контексте для админа {admin_user_id} в состоянии waiting_for_edit_choice."
        )
        await query.answer(
            "Произошла ошибка при редактировании услуги. ID услуги не найден.",
            show_alert=True,
        )
        await state.clear()
        return

    prompt_message = ""
    next_state = None

    if field_name == "name":
        prompt_message = (
            "✏️ **Редактирование названия услуги.**\n\nВведите новое название услуги:"
        )
        next_state = AdminServiceStates.waiting_for_new_service_name
    elif field_name == "price":
        prompt_message = "💰 **Редактирование цены услуги.**\n\nВведите новую цену услуги (можно пропустить, написав '-'):"
        next_state = AdminServiceStates.waiting_for_new_service_price
    elif field_name == "description":
        prompt_message = "📝 **Редактирование описания услуги.**\n\nВведите новое описание услуги (можно пропустить, написав '-'):"
        next_state = AdminServiceStates.waiting_for_new_service_description
    elif field_name == "duration":
        prompt_message = "⏱ **Редактирование длительности услуги.**\n\nВведите новую длительность в минутах (например, 60):"
        next_state = AdminServiceStates.waiting_for_service_duration
    else:
        logging.warning(
            f"Админ {admin_user_id} выбрал неизвестное поле для редактирования: '{field_name}'. Callback: {query.data}"
        )
        await query.answer("Неизвестное поле для редактирования.", show_alert=True)
        return

    try:
        await query.message.edit_text(prompt_message, parse_mode="Markdown")
        await state.set_state(next_state)
        logging.info(
            f"Админ {admin_user_id} переведен в состояние {next_state} для ввода нового значения поля '{field_name}'."
        )
        await query.answer(
            f"Ожидаю новое значение для поля '{field_name}'.", show_alert=False
        )

    except Exception as e:
        logging.error(
            f"Ошибка при переходе в состояние ввода нового значения для админа {admin_user_id}: {e}"
        )
        await query.answer(
            "Произошла ошибка при переходе к вводу данных.", show_alert=True
        )
        await state.clear()


@router.message(AdminServiceStates.waiting_for_new_service_name, F.text)
async def process_admin_new_service_name(message: Message, state: FSMContext):
    """
    Обрабатывает ввод нового названия услуги админом в состоянии AdminServiceStates.waiting_for_new_service_name.
    Сохраняет новое название в БД и сообщает результат.
    """
    admin_user_id = message.from_user.id
    new_name = message.text.strip()

    logging.info(
        f"Админ {admin_user_id} ввел новое название услуги для редактирования: '{new_name}'."
    )

    if not new_name:
        await message.answer(
            "Название услуги не может быть пустым. Пожалуйста, введите новое название:"
        )
        return

    data = await state.get_data()
    editing_service_id = data.get("editing_service_id")

    if editing_service_id is None:
        logging.error(
            f"Ошибка FSM: ID услуги для редактирования не найден в контексте для админа {admin_user_id} при вводе нового названия."
        )
        await message.answer(
            "Произошла ошибка при редактировании услуги. ID услуги не найден."
        )
        await state.clear()
        return

    updated = False
    try:
        async with async_session_factory() as session:
            service_repo = ServiceRepository(session)
            service_service = ServiceService(service_repo)

            updates = {"name": new_name}
            updated = await service_service.update_service(editing_service_id, updates)

        if updated:
            logging.info(
                f"Название услуги ID={editing_service_id} успешно обновлено на '{new_name}' админом {admin_user_id}."
            )
            await message.answer(
                f"✅ Название услуги ID=`{editing_service_id}` успешно обновлено на: **{new_name}**",
                parse_mode="Markdown",
            )
        else:
            logging.warning(
                f"Не удалось обновить название услуги ID={editing_service_id} на '{new_name}' (админ {admin_user_id})."
            )
            await message.answer(
                f"❌ Не удалось обновить название услуги ID=`{editing_service_id}`. Возможно, услуга не найдена.",
                parse_mode="Markdown",
            )

    except Exception as e:
        logging.error(
            f"Критическая ошибка при обновлении названия услуги ID={editing_service_id} админом {admin_user_id}: {e}"
        )
        await message.answer(
            "Произошла ошибка при сохранении нового названия услуги. Пожалуйста, попробуйте еще раз."
        )
    finally:
        await state.clear()
        logging.info(
            f"Состояние FSM редактирования услуги очищено после ввода названия для админа {admin_user_id}."
        )


@router.message(AdminServiceStates.waiting_for_new_service_price, F.text)
async def process_admin_new_service_price(message: Message, state: FSMContext):
    """
    Обрабатывает ввод новой цены услуги админом в состоянии AdminServiceStates.waiting_for_new_service_price.
    Сохраняет новую цену в БД (или None) и сообщает результат.
    """
    admin_user_id = message.from_user.id
    new_price_input = message.text.strip()

    logging.info(
        f"Админ {admin_user_id} ввел новую цену услуги для редактирования: '{new_price_input}'."
    )

    new_price = None

    if new_price_input != "-":
        new_price = new_price_input

    data = await state.get_data()
    editing_service_id = data.get("editing_service_id")

    if editing_service_id is None:
        logging.error(
            f"Ошибка FSM: ID услуги для редактирования не найден в контексте для админа {admin_user_id} при вводе новой цены."
        )
        await message.answer(
            "Произошла ошибка при редактировании услуги. ID услуги не найден."
        )
        await state.clear()
        return

    updated = False
    try:
        async with async_session_factory() as session:
            service_repo = ServiceRepository(session)
            service_service = ServiceService(service_repo)

            updates = {"price": new_price}
            updated = await service_service.update_service(editing_service_id, updates)

        if updated:
            logging.info(
                f"Цена услуги ID={editing_service_id} успешно обновлена на '{new_price}' админом {admin_user_id}."
            )
            await message.answer(
                f"✅ Цена услуги ID=`{editing_service_id}` успешно обновлена на: **{new_price if new_price else 'Не указано'}**",
                parse_mode="Markdown",
            )
        else:
            logging.warning(
                f"Не удалось обновить цену услуги ID={editing_service_id} на '{new_price}' (админ {admin_user_id})."
            )
            await message.answer(
                f"❌ Не удалось обновить цену услуги ID=`{editing_service_id}`. Возможно, услуга не найдена.",
                parse_mode="Markdown",
            )

    except Exception as e:
        logging.error(
            f"Критическая ошибка при обновлении цены услуги ID={editing_service_id} админом {admin_user_id}: {e}"
        )
        await message.answer(
            "Произошла ошибка при сохранении новой цены услуги. Пожалуйста, попробуйте еще раз."
        )
    finally:
        await state.clear()
        logging.info(
            f"Состояние FSM редактирования услуги очищено после ввода цены для админа {admin_user_id}."
        )


@router.message(AdminServiceStates.waiting_for_new_service_description, F.text)
async def process_admin_new_service_description(message: Message, state: FSMContext):
    """
    Обрабатывает ввод нового описания услуги админом в состоянии AdminServiceStates.waiting_for_new_service_description.
    Сохраняет новое описание в БД (или None) и сообщает результат.
    """
    admin_user_id = message.from_user.id
    new_description_input = message.text.strip()

    logging.info(
        f"Админ {admin_user_id} ввел новое описание услуги для редактирования: '{new_description_input}'."
    )

    new_description = None

    if new_description_input != "-":
        new_description = new_description_input

    data = await state.get_data()
    editing_service_id = data.get("editing_service_id")

    if editing_service_id is None:
        logging.error(
            f"Ошибка FSM: ID услуги для редактирования не найден в контексте для админа {admin_user_id} при вводе нового описания."
        )
        await message.answer(
            "Произошла ошибка при редактировании услуги. ID услуги не найден."
        )
        await state.clear()
        return

    updated = False
    try:
        async with async_session_factory() as session:
            service_repo = ServiceRepository(session)
            service_service = ServiceService(service_repo)

            updates = {"description": new_description}
            updated = await service_service.update_service(editing_service_id, updates)

        if updated:
            logging.info(
                f"Описание услуги ID={editing_service_id} успешно обновлено на '{new_description}' админом {admin_user_id}."
            )
            await message.answer(
                f"✅ Описание услуги ID=`{editing_service_id}` успешно обновлено на: **{new_description if new_description else 'Не указано'}**",
                parse_mode="Markdown",
            )
        else:
            logging.warning(
                f"Не удалось обновить описание услуги ID={editing_service_id} на '{new_description}' (админ {admin_user_id})."
            )
            await message.answer(
                f"❌ Не удалось обновить описание услуги ID=`{editing_service_id}`. Возможно, услуга не найдена.",
                parse_mode="Markdown",
            )

    except Exception as e:
        logging.error(
            f"Критическая ошибка при обновлении описания услуги ID={editing_service_id} админом {admin_user_id}: {e}"
        )
        await message.answer(
            "Произошла ошибка при сохранении нового описания услуги. Пожалуйста, попробуйте еще раз."
        )
    finally:
        await state.clear()
        logging.info(
            f"Состояние FSM редактирования услуги очищено после ввода описания для админа {admin_user_id}."
        )


@router.message(AdminServiceStates.waiting_for_service_duration, F.text)
async def process_admin_new_service_duration(message: Message, state: FSMContext):
    """
    Обрабатывает ввод новой длительности услуги админом.
    """
    admin_user_id = message.from_user.id
    new_duration_text = message.text.strip()

    try:
        new_duration = int(new_duration_text)
        if new_duration <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Пожалуйста, введите положительное целое число (минуты).")
        return

    data = await state.get_data()
    editing_service_id = data.get("editing_service_id")

    if editing_service_id is None:
        logging.error(
            f"Ошибка FSM: ID услуги для редактирования не найден в контексте для админа {admin_user_id} при вводе новой длительности."
        )
        await message.answer(
            "Произошла ошибка при редактировании услуги. ID услуги не найден."
        )
        await state.clear()
        return

    updated = False
    try:
        async with async_session_factory() as session:
            service_repo = ServiceRepository(session)
            service_service = ServiceService(service_repo)
            updates = {"duration": new_duration}
            updated = await service_service.update_service(editing_service_id, updates)

        if updated:
            logging.info(
                f"Длительность услуги ID={editing_service_id} успешно обновлена на {new_duration} мин админом {admin_user_id}."
            )
            await message.answer(
                f"✅ Длительность услуги ID=`{editing_service_id}` успешно обновлена на: **{new_duration} мин**",
                parse_mode="Markdown",
            )
        else:
            logging.warning(
                f"Не удалось обновить длительность услуги ID={editing_service_id} (админ {admin_user_id})."
            )
            await message.answer(
                f"❌ Не удалось обновить длительность услуги ID=`{editing_service_id}`. Возможно, услуга не найдена.",
                parse_mode="Markdown",
            )

    except Exception as e:
        logging.error(
            f"Критическая ошибка при обновлении длительности услуги ID={editing_service_id} админом {admin_user_id}: {e}"
        )
        await message.answer(
            "Произошла ошибка при сохранении новой длительности услуги. Пожалуйста, попробуйте еще раз.",
            parse_mode="Markdown",
        )
    finally:
        await state.clear()
        logging.info(
            f"Состояние FSM редактирования услуги очищено после ввода длительности для админа {admin_user_id}."
        )


@router.message(
    Command("admin_add_employee"), ~StateFilter(AdminServiceStates, AdminEmployeeStates)
)
async def admin_add_employee_cmd(message: Message, state: FSMContext):
    """
    Админская команда для начала добавления нового сотрудника.
    Переводит админа в состояние ожидания имени сотрудника.
    """
    admin_user_id = message.from_user.id
    logging.info(f"Админ {admin_user_id} начал процесс добавления сотрудника.")

    await state.clear()

    await state.set_state(AdminEmployeeStates.waiting_for_employee_name)

    await message.answer(
        "✍️ **Добавление нового сотрудника.**\n\nВведите имя сотрудника:",
        parse_mode="Markdown",
    )


@router.message(AdminEmployeeStates.waiting_for_employee_name, F.text)
async def process_admin_employee_name(message: Message, state: FSMContext):
    """
    Обрабатывает ввод имени сотрудника админом в состоянии AdminEmployeeStates.waiting_for_employee_name.
    Сохраняет имя в FSM контекст и переходит в состояние ожидания специальности.
    """
    admin_user_id = message.from_user.id
    employee_name = message.text.strip()

    logging.info(f"Админ {admin_user_id} ввел имя сотрудника: '{employee_name}'.")

    if not employee_name:
        await message.answer(
            "Имя сотрудника не может быть пустым. Пожалуйста, введите имя:"
        )
        return

    await state.update_data(new_employee_name=employee_name)
    logging.info(
        f"Имя сотрудника '{employee_name}' сохранено в FSM для админа {admin_user_id}."
    )

    await state.set_state(AdminEmployeeStates.waiting_for_employee_specialty)

    await message.answer(
        "🧑‍⚕️ **Добавление нового сотрудника.**\n\nТеперь введите специальность сотрудника (например, 'Терапевт').\n\nЕсли специальность не нужна, просто отправьте символ `-` (тире).",
        parse_mode="Markdown",
    )


@router.message(AdminEmployeeStates.waiting_for_employee_specialty, F.text)
async def process_admin_employee_specialty(message: Message, state: FSMContext):
    """
    Обрабатывает ввод специальности сотрудника админом в состоянии AdminEmployeeStates.waiting_for_employee_specialty.
    Сохраняет специальность (или None), собирает все данные из FSM и создает сотрудника в БД.
    """
    admin_user_id = message.from_user.id
    employee_specialty_input = message.text.strip()

    logging.info(
        f"Админ {admin_user_id} ввел специальность сотрудника: '{employee_specialty_input}'."
    )

    employee_specialty = None

    if employee_specialty_input == "-":
        logging.info(f"Админ {admin_user_id} пропустил ввод специальности сотрудника.")
    else:
        employee_specialty = employee_specialty_input

    await state.update_data(new_employee_specialty=employee_specialty)
    logging.info(
        f"Специальность сотрудника '{employee_specialty}' сохранена в FSM для админа {admin_user_id}."
    )

    employee_data = await state.get_data()
    new_employee_name = employee_data.get("new_employee_name")
    new_employee_specialty = employee_data.get("new_employee_specialty")

    logging.info(
        f"Админ {admin_user_id} завершил ввод данных для нового сотрудника. Попытка создания: Имя='{new_employee_name}', Специальность='{new_employee_specialty}'."
    )

    if not new_employee_name:
        logging.error(
            f"Ошибка FSM: Имя сотрудника не найдено в контексте для админа {admin_user_id}. Отмена процесса добавления сотрудника."
        )
        await message.answer(
            "Произошла ошибка при сборе данных. Имя сотрудника отсутствует. Пожалуйста, начните добавление сотрудника заново /admin_add_employee.",
            parse_mode="Markdown",
        )
        await state.clear()
        return

    added_employee = None
    try:
        async with async_session_factory() as session:
            employee_repo = EmployeeRepository(session)
            employee_service = EmployeeService(employee_repo)

            added_employee = await employee_service.add_employee(
                name=new_employee_name, specialty=new_employee_specialty
            )

        if added_employee:
            logging.info(
                f"Новый сотрудник успешно добавлен в БД админом {admin_user_id}: ID={added_employee.id}, Имя='{added_employee.name}'."
            )
            await message.answer(
                f"✅ Новый сотрудник успешно добавлен!\n\n"
                f"**Имя:** {added_employee.name}\n"
                f"**Специальность:** {added_employee.specialty if added_employee.specialty else 'Не указана'}",
                parse_mode="Markdown",
            )
            await message.answer(
                "**Следующий шаг:** Теперь необходимо связать этого сотрудника с услугами, которые он предоставляет.",
                parse_mode="Markdown",
            )

        else:
            logging.warning(
                f"Сервис не смог добавить сотрудника для админа {admin_user_id}: Имя='{new_employee_name}'."
            )
            await message.answer(
                f"❌ Не удалось добавить сотрудника '{new_employee_name}'. Проверьте логи на наличие ошибок.",
                parse_mode="Markdown",
            )

    except Exception as e:
        logging.error(
            f"Критическая ошибка при сохранении нового сотрудника в БД для админа {admin_user_id}: {e}"
        )
        await message.answer(
            "Произошла ошибка при сохранении сотрудника. Пожалуйста, попробуйте еще раз или свяжитесь с разработчиком.",
            parse_mode="Markdown",
        )
    finally:
        await state.clear()
        logging.info(
            f"Состояние FSM добавления сотрудника очищено для админа {admin_user_id}."
        )


@router.message(
    Command("admin_manage_employee_services"),
    ~StateFilter(AdminServiceStates, AdminEmployeeStates),
)
async def admin_manage_employee_services_cmd(message: Message, state: FSMContext):
    """
    Админская команда для начала управления услугами, которые оказывает сотрудник.
    Показывает список сотрудников для выбора.
    """
    admin_user_id = message.from_user.id
    logging.info(
        f"Админ {admin_user_id} начал процесс управления услугами сотрудников."
    )

    await state.clear()

    employees = []
    try:
        async with async_session_factory() as session:
            employee_repo = EmployeeRepository(session)
            employee_service = EmployeeService(employee_repo)
            employees = await employee_service.get_all_employees()

    except Exception as e:
        logging.error(
            f"Ошибка при получении списка сотрудников для админа {admin_user_id} (управление услугами): {e}"
        )
        await message.answer("Произошла ошибка при загрузке списка сотрудников.")
        return

    if not employees:
        await message.answer(
            "В базе данных пока нет сотрудников для управления их услугами."
        )
        await message.answer(
            "Вы можете добавить нового сотрудника командой /admin_add_employee",
            parse_mode="Markdown",
        )
        return

    unique_employees_by_name = {}

    for employee in employees:
        if employee.name not in unique_employees_by_name:
            unique_employees_by_name[employee.name] = employee

    filtered_employees = list(unique_employees_by_name.values())

    filtered_employees.sort(key=lambda emp: emp.name)

    # --- ОТЛАДОЧНЫЕ ЛОГИ ---
    logging.info(
        f"DEBUG HANDLER: admin_manage_employee_services_cmd получил {len(employees)} сырых сотрудников."
    )
    employee_list_debug_raw = [(emp.id, emp.name) for emp in employees]
    logging.info(f"DEBUG HANDLER: Список сырых сотрудников: {employee_list_debug_raw}")

    logging.info(
        f"DEBUG HANDLER: admin_manage_employee_services_cmd получил {len(filtered_employees)} отфильтрованных сотрудников."
    )
    employee_list_debug_filtered = [(emp.id, emp.name) for emp in filtered_employees]
    logging.info(
        f"DEBUG HANDLER: Список отфильтрованных сотрудников: {employee_list_debug_filtered}"
    )
    # --- КОНЕЦ ОТЛАДОЧНЫХ ЛОГОВ ---

    management_keyboard = create_admin_employee_association_keyboard(filtered_employees)

    if management_keyboard:
        await message.answer(
            "🧑‍⚕️ **Управление услугами сотрудников:**\n\nВыберите сотрудника, услуги которого хотите изменить:",
            parse_mode="Markdown",
            reply_markup=management_keyboard,
        )
        await state.set_state(AdminEmployeeStates.waiting_for_employee_for_association)
        logging.info(
            f"Админ {admin_user_id} переведен в состояние {AdminEmployeeStates.waiting_for_employee_for_association}."
        )
    else:
        await message.answer(
            "Не удалось создать клавиатуру сотрудников для управления услугами. Нет уникальных сотрудников по имени."
        )
        logging.warning(
            f"create_admin_employee_association_keyboard вернула None после фильтрации по имени для админа {admin_user_id}."
        )


@router.callback_query(
    AdminEmployeeStates.waiting_for_employee_for_association,
    F.data.startswith("admin_manage_employee_services_"),
)
async def admin_select_employee_for_association(
    query: CallbackQuery, state: FSMContext
):
    """
    Обрабатывает выбор сотрудника из списка для управления его услугами.
    Извлекает ID сотрудника, сохраняет его, получает список всех услуг и услуг сотрудника,
    и показывает клавиатуру для управления связями услуг.
    """
    admin_user_id = query.from_user.id
    employee_id_str = query.data.split("_")[4]

    try:
        employee_id = int(employee_id_str)
        if employee_id <= 0:
            raise ValueError("ID сотрудника должен быть положительным числом.")
    except ValueError as e:
        logging.warning(
            f"Админ {admin_user_id} получил неверный ID сотрудника из callback для управления услугами: '{query.data}'. Ошибка: {e}"
        )
        await query.answer("Неверный формат ID сотрудника.", show_alert=True)
        return

    logging.info(
        f"Админ {admin_user_id} выбрал сотрудника ID={employee_id} для управления услугами."
    )

    employee_to_manage = None  # Объект выбранного сотрудника
    all_services = []  # Список всех услуг
    employee_services_ids = set()

    try:
        async with async_session_factory() as session:
            employee_repo = EmployeeRepository(session)
            employee_service = EmployeeService(employee_repo)
            service_repo = ServiceRepository(session)
            service_service = ServiceService(service_repo)

            employee_to_manage = await employee_service.get_employee_by_id(employee_id)

            if not employee_to_manage:
                logging.warning(
                    f"Админ {admin_user_id} попытался управлять услугами несуществующего сотрудника ID={employee_id}."
                )
                await query.answer("Сотрудник не найден.", show_alert=True)
                return

            all_services = await service_service.get_all_services()

            employee_services_ids = {
                service.id for service in employee_to_manage.services
            }

    except Exception as e:
        logging.error(
            f"Ошибка при получении данных для управления услугами сотрудника ID={employee_id} админом {admin_user_id}: {e}"
        )
        await query.answer("Произошла ошибка при загрузке данных.", show_alert=True)
        await state.clear()
        return

    await state.update_data(managing_employee_id=employee_id)
    logging.info(
        f"ID управляемого сотрудника {employee_id} сохранен в FSM для админа {admin_user_id}."
    )

    association_keyboard = create_employee_service_toggle_keyboard(
        all_services, employee_services_ids, employee_id
    )

    if not association_keyboard:
        await query.answer("Нет услуг для управления.", show_alert=True)
        return

    try:
        await query.message.edit_text(
            f"🧑‍⚕️ **Управление услугами для {employee_to_manage.name}:**\n\n"
            f"Нажмите на услугу, чтобы добавить или убрать ее из списка услуг этого сотрудника.\n"
            f"✅ = сотрудник оказывает услугу\n"
            f"⬜ = сотрудник не оказывает услугу",
            parse_mode="Markdown",
            reply_markup=association_keyboard,
        )
        await state.set_state(
            AdminEmployeeStates.waiting_for_service_association_choice
        )
        logging.info(
            f"Админ {admin_user_id} переведен в состояние {AdminEmployeeStates.waiting_for_service_association_choice}."
        )
        await query.answer("Выберите услуги для управления.", show_alert=False)

    except Exception as e:
        logging.error(
            f"Ошибка при переходе в состояние управления услугами сотрудника для админа {admin_user_id}: {e}"
        )
        await query.answer(
            "Произошла ошибка при переходе к управлению услугами.", show_alert=True
        )
        await state.clear()


@router.callback_query(
    AdminEmployeeStates.waiting_for_service_association_choice,
    F.data.startswith("admin_toggle_association_"),
)
async def admin_toggle_employee_service_association(
    query: CallbackQuery, state: FSMContext
):
    """
    Обрабатывает нажатие кнопки услуги для переключения связи с выбранным сотрудником.
    Добавляет или удаляет связь в БД, сообщает результат и обновляет клавиатуру.
    """
    admin_user_id = query.from_user.id
    try:
        parts = query.data.split("_")
        if len(parts) != 5:
            raise ValueError("Invalid callback data format.")

        employee_id_str = parts[3]
        service_id_str = parts[4]

        employee_id = int(employee_id_str)
        service_id = int(service_id_str)

        if employee_id <= 0 or service_id <= 0:
            raise ValueError(
                "ID сотрудника или услуги должен быть положительным числом."
            )

    except ValueError as e:
        logging.warning(
            f"Админ {admin_user_id} получил неверный ID сотрудника/услуги из callback для переключения связи: '{query.data}'. Ошибка: {e}"
        )
        await query.answer(
            "Неверный формат данных. Пожалуйста, выберите снова.", show_alert=True
        )
        return

    logging.info(
        f"Админ {admin_user_id} нажал кнопку переключения связи для сотрудника ID={employee_id} и услуги ID={service_id}."
    )

    data = await state.get_data()
    managing_employee_id_fsm = data.get("managing_employee_id")

    if managing_employee_id_fsm is None or managing_employee_id_fsm != employee_id:
        logging.error(
            f"Ошибка FSM: ID управляемого сотрудника в контексте ({managing_employee_id_fsm}) не совпадает с ID из callback ({employee_id}) для админа {admin_user_id} при переключении связи."
        )
        await query.answer(
            "Произошла ошибка. Пожалуйста, начните управление услугами сотрудника заново.",
            show_alert=True,
        )
        await state.clear()
        await query.message.edit_text(
            "Произошла внутренняя ошибка. Пожалуйста, начните управление снова.",
            reply_markup=None,
        )
        return

    feedback_message = ""
    operation_successful = False

    try:
        async with async_session_factory() as session:
            employee_repo = EmployeeRepository(session)
            employee_service = EmployeeService(employee_repo)
            service_repo = ServiceRepository(session)
            service_service = ServiceService(service_repo)

            assoc_exists_result = await session.execute(
                select(employee_service_association).where(
                    and_(
                        employee_service_association.c.employee_id == employee_id,
                        employee_service_association.c.service_id == service_id,
                    )
                )
            )
            association_exists = assoc_exists_result.first() is not None

            if association_exists:
                logging.info(
                    f"Связь найдена. Удаляем: Сотрудник ID={employee_id}, Услуга ID={service_id}."
                )
                operation_successful = (
                    await employee_service.remove_service_from_employee(
                        employee_id, service_id
                    )
                )
                if operation_successful:
                    feedback_message = "❌ Услуга убрана у сотрудника."
                    logging.info(
                        f"Связь успешно удалена для сотрудника ID={employee_id}, услуги ID={service_id}."
                    )
                else:
                    feedback_message = "❗ Не удалось убрать услугу."
                    logging.warning(
                        f"Ошибка при удалении связи для сотрудника ID={employee_id}, услуги ID={service_id}."
                    )

            else:
                logging.info(
                    f"Связь не найдена. Добавляем: Сотрудник ID={employee_id}, Услуга ID={service_id}."
                )
                operation_successful = await employee_service.add_service_to_employee(
                    employee_id, service_id
                )
                if operation_successful:
                    feedback_message = "✅ Услуга добавлена сотруднику."
                    logging.info(
                        f"Связь успешно добавлена для сотрудника ID={employee_id}, услуги ID={service_id}."
                    )
                else:
                    feedback_message = (
                        "❗ Не удалось добавить услугу (возможно, уже добавлена)."
                    )
                    logging.warning(
                        f"Ошибка при добавлении связи для сотрудника ID={employee_id}, услуги ID={service_id}."
                    )

            employee_to_manage_updated = await employee_service.get_employee_by_id(
                employee_id
            )

            if not employee_to_manage_updated:
                logging.error(
                    f"Ошибка при повторном получении сотрудника ID={employee_id} после переключения связи для админа {admin_user_id}."
                )
                await state.clear()
                await query.message.edit_text(
                    "Произошла ошибка при обновлении списка услуг.", reply_markup=None
                )
                await query.answer("Ошибка.", show_alert=True)
                return

            updated_employee_services_ids = {
                service.id for service in employee_to_manage_updated.services
            }

            all_services = await service_service.get_all_services()

            updated_keyboard = create_employee_service_toggle_keyboard(
                all_services, updated_employee_services_ids, employee_id
            )

            if updated_keyboard:
                await query.message.edit_reply_markup(reply_markup=updated_keyboard)
            else:
                await query.message.edit_text(
                    "Нет услуг для управления.", reply_markup=None
                )

    except Exception as e:
        logging.error(
            f"Критическая ошибка при переключении связи для сотрудника ID={employee_id}, услуги ID={service_id} админом {admin_user_id}: {e}"
        )
        feedback_message = "Произошла ошибка."
        await state.clear()
        await query.message.edit_text(
            "Произошла внутренняя ошибка. Пожалуйста, начните управление снова.",
            reply_markup=None,
        )

    await query.answer(feedback_message, show_alert=False)


@router.callback_query(
    AdminEmployeeStates.waiting_for_service_association_choice,
    F.data == "admin_done_managing_services",
)
async def admin_done_managing_services(query: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие кнопки "Готово" в режиме управления услугами сотрудника.
    Очищает состояние FSM и сообщает об окончании.
    """
    admin_user_id = query.from_user.id
    logging.info(f"Админ {admin_user_id} завершил управление услугами сотрудника.")

    await state.clear()
    logging.info("Состояние FSM управления услугами сотрудника очищено.")

    await query.message.edit_text(
        "✅ Управление услугами сотрудника завершено.", reply_markup=None
    )

    await query.answer("Готово.", show_alert=False)


@router.message(
    Command("admin_employees"), ~StateFilter(AdminServiceStates, AdminEmployeeStates)
)
async def admin_list_employees_cmd(message: Message, state: FSMContext):
    """
    Админская команда для просмотра списка сотрудников с кнопками для редактирования/удаления.
    """
    admin_user_id = message.from_user.id
    logging.info(f"Админ {admin_user_id} запросил список сотрудников для управления.")

    employees = []
    try:
        async with async_session_factory() as session:
            employee_repo = EmployeeRepository(session)
            employee_service = EmployeeService(employee_repo)

            employees = await employee_service.get_all_employees()

    except Exception as e:
        logging.error(
            f"Ошибка при получении списка сотрудников для админа {admin_user_id} (управление): {e}"
        )
        await message.answer(
            "Произошла ошибка при загрузке списка сотрудников для управления."
        )
        return

    if not employees:
        await message.answer("В базе данных пока нет сотрудников для управления.")
        await message.answer(
            "Вы можете добавить нового сотрудника командой /admin_add_employee",
            parse_mode="Markdown",
        )
        return

    management_keyboard = create_admin_employee_management_keyboard(employees)

    if management_keyboard:
        await message.answer(
            "🧑‍⚕️ **Управление сотрудниками:**\n\nВыберите сотрудника для редактирования или удаления:",
            parse_mode="Markdown",
            reply_markup=management_keyboard,
        )
        await state.set_state(
            AdminEmployeeStates.waiting_for_employee_management_choice
        )
        logging.info(
            f"Админ {admin_user_id} переведен в состояние {AdminEmployeeStates.waiting_for_employee_management_choice}."
        )
    else:
        logging.warning(
            f"create_admin_employee_management_keyboard вернула None (возможно, из-за фильтрации дубликатов по имени) для админа {admin_user_id}."
        )
        await message.answer(
            "Не удалось создать клавиатуру управления сотрудниками. Возможно, все сотрудники в базе имеют дубликаты имен."
        )


@router.callback_query(
    AdminEmployeeStates.waiting_for_employee_management_choice,
    F.data.startswith("admin_edit_employee_"),
)
async def admin_select_employee_to_edit(query: CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор сотрудника для редактирования из списка управления сотрудниками.
    Извлекает ID сотрудника, сохраняет его и предлагает выбрать поле для редактирования.
    """
    admin_user_id = query.from_user.id  # Получаем ID админа
    employee_id_str = query.data.split("_")[3]

    try:
        employee_id = int(employee_id_str)
        if employee_id <= 0:
            raise ValueError("ID сотрудника должен быть положительным числом.")
    except ValueError as e:
        logging.warning(
            f"Админ {admin_user_id} получил неверный ID сотрудника из callback для редактирования: '{query.data}'. Ошибка: {e}"
        )
        await query.answer("Неверный формат ID сотрудника.", show_alert=True)
        return

    logging.info(
        f"Админ {admin_user_id} выбрал сотрудника ID={employee_id} для редактирования."
    )

    employee_to_edit = None  # Инициализируем
    try:
        async with async_session_factory() as session:
            employee_repo = EmployeeRepository(session)
            employee_service = EmployeeService(employee_repo)
            employee_to_edit = await employee_service.get_employee_by_id(employee_id)

        if not employee_to_edit:
            logging.warning(
                f"Админ {admin_user_id} попытался отредактировать несуществующего сотрудника ID={employee_id}."
            )
            await query.answer("Сотрудник не найден.", show_alert=True)
            return

    except Exception as e:
        logging.error(
            f"Ошибка при проверке сотрудника ID={employee_id} для редактирования админом {admin_user_id}: {e}"
        )
        await query.answer(
            "Произошла ошибка при подготовке к редактированию.", show_alert=True
        )
        return

    await state.update_data(editing_employee_id=employee_id)
    logging.info(
        f"ID редактируемого сотрудника {employee_id} сохранен в FSM для админа {admin_user_id}."
    )

    edit_field_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Имя", callback_data="admin_edit_employee_field_name"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Специальность",
                    callback_data="admin_edit_employee_field_specialty",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Отмена редактирования",
                    callback_data="admin_cancel_edit_employee",
                )
            ],
        ]
    )

    await query.message.edit_text(
        f"✏️ **Редактирование сотрудника:**\n\n"
        f"**Имя:** {employee_to_edit.name}\n"
        f"**Специальность:** {employee_to_edit.specialty if employee_to_edit.specialty else 'Не указана'}\n\n"
        f"Выберите, что хотите изменить:",
        parse_mode="Markdown",
        reply_markup=edit_field_keyboard,
    )

    await state.set_state(AdminEmployeeStates.waiting_for_employee_edit_choice)
    logging.info(
        f"Админ {admin_user_id} переведен в состояние {AdminEmployeeStates.waiting_for_employee_edit_choice}."
    )

    await query.answer("Выберите поле для редактирования.", show_alert=False)


@router.callback_query(
    AdminEmployeeStates.waiting_for_employee_management_choice,
    F.data.startswith("admin_delete_employee_"),
)
async def admin_select_employee_to_delete(query: CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор сотрудника для удаления из списка управления сотрудниками.
    Извлекает ID сотрудника, сохраняет его и запрашивает подтверждение удаления.
    """
    admin_user_id = query.from_user.id
    employee_id_str = query.data.split("_")[3]

    try:
        employee_id = int(employee_id_str)
        if employee_id <= 0:
            raise ValueError("ID сотрудника должен быть положительным числом.")
    except ValueError as e:
        logging.warning(
            f"Админ {admin_user_id} получил неверный ID сотрудника из callback для удаления: '{query.data}'. Ошибка: {e}"
        )
        await query.answer("Неверный формат ID сотрудника.", show_alert=True)
        return

    logging.info(
        f"Админ {admin_user_id} выбрал сотрудника ID={employee_id} для удаления."
    )

    employee_to_delete = None
    try:
        async with async_session_factory() as session:
            employee_repo = EmployeeRepository(session)
            employee_service = EmployeeService(employee_repo)
            employee_to_delete = await employee_service.get_employee_by_id(employee_id)

        if not employee_to_delete:
            logging.warning(
                f"Админ {admin_user_id} попытался удалить несуществующего сотрудника ID={employee_id}."
            )
            await query.answer("Сотрудник не найден.", show_alert=True)
            return

    except Exception as e:
        logging.error(
            f"Ошибка при проверке сотрудника ID={employee_id} для удаления админом {admin_user_id}: {e}"
        )
        await query.answer(
            "Произошла ошибка при подготовке к удалению.", show_alert=True
        )
        return

    await state.update_data(deleting_employee_id=employee_id)
    logging.info(
        f"ID удаляемого сотрудника {employee_id} сохранен в FSM для админа {admin_user_id}."
    )

    confirm_delete_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"✅ Да, удалить сотрудника '{employee_to_delete.name}'",
                    callback_data="admin_confirm_delete_employee",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Нет, отмена", callback_data="admin_cancel_delete_employee"
                )
            ],
        ]
    )

    employee_to_delete = None
    try:
        async with async_session_factory() as session:
            employee_repo = EmployeeRepository(session)
            employee_service = EmployeeService(employee_repo)
            employee_to_delete = await employee_service.get_employee_by_id(employee_id)

        if not employee_to_delete:
            logging.warning(
                f"Админ {admin_user_id} попытался удалить несуществующего сотрудника ID={employee_id}."
            )
            await query.answer("Сотрудник не найден.", show_alert=True)
            return

    except Exception as e:
        logging.error(
            f"Ошибка при проверке сотрудника ID={employee_id} для удаления админом {admin_user_id}: {e}"
        )
        await query.answer(
            "Произошла ошибка при подготовке к удалению.", show_alert=True
        )
        return

    await state.update_data(deleting_employee_id=employee_id)  # <-- Сохраняем ID
    logging.info(
        f"ID удаляемого сотрудника {employee_id} сохранен в FSM для админа {admin_user_id}."
    )

    confirm_delete_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"✅ Да, удалить сотрудника '{employee_to_delete.name}'",
                    callback_data="admin_confirm_delete_employee",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Нет, отмена", callback_data="admin_cancel_delete_employee"
                )
            ],
        ]
    )

    await query.message.edit_text(
        f"🗑️ **Удаление сотрудника:**\n\n"
        f"Вы собираетесь удалить сотрудника:\n"
        f"**Имя:** {employee_to_delete.name}\n"
        f"**Специальность:** {employee_to_delete.specialty if employee_to_delete.specialty else 'Не указана'}\n\n"
        f"**Вы уверены?** Это действие нельзя отменить.",
        parse_mode="Markdown",
        reply_markup=confirm_delete_keyboard,
    )

    await state.set_state(AdminEmployeeStates.confirm_delete_employee)
    logging.info(
        f"Админ {admin_user_id} переведен в состояние {AdminEmployeeStates.confirm_delete_employee}."
    )

    await query.answer()


@router.callback_query(
    AdminEmployeeStates.confirm_delete_employee,
    F.data == "admin_confirm_delete_employee",
)
async def admin_confirm_delete_employee(query: CallbackQuery, state: FSMContext):
    """
    Обрабатывает подтверждение удаления сотрудника админом.
    Удаляет сотрудника из базы данных и сообщает результат.
    """
    admin_user_id = query.from_user.id
    logging.info(f"Админ {admin_user_id} подтвердил удаление сотрудника.")

    data = await state.get_data()
    employee_id_to_delete = data.get("deleting_employee_id")

    if employee_id_to_delete is None:
        logging.error(
            f"Ошибка FSM: ID сотрудника для удаления не найден в контексте для админа {admin_user_id} в состоянии confirm_delete_employee."
        )
        await query.answer(
            "Произошла ошибка при удалении сотрудника. ID сотрудника не найден.",
            show_alert=True,
        )
        await state.clear()
        await query.message.edit_text(
            "Процесс удаления прерван из-за ошибки.", reply_markup=None
        )
        return

    deleted = False
    try:
        async with async_session_factory() as session:
            employee_repo = EmployeeRepository(session)
            employee_service = EmployeeService(employee_repo)

            deleted = await employee_service.delete_employee(employee_id_to_delete)

        if deleted:
            logging.info(
                f"Сотрудник ID={employee_id_to_delete} успешно удален из БД админом {admin_user_id}."
            )
            await query.message.edit_text(
                f"✅ Сотрудник ID=`{employee_id_to_delete}` успешно удален.",
                parse_mode="Markdown",
            )
        else:
            logging.warning(
                f"Попытка удаления сотрудника ID={employee_id_to_delete}, но сотрудник не найден в БД при вызове delete_employee (админ {admin_user_id})."
            )
            await query.message.edit_text(
                f"❌ Сотрудник ID=`{employee_id_to_delete}` не найден или уже удален.",
                parse_mode="Markdown",
            )

    except Exception as e:
        logging.error(
            f"Критическая ошибка при удалении сотрудника ID={employee_id_to_delete} админом {admin_user_id}: {e}"
        )
        await query.message.edit_text(
            "Произошла ошибка при удалении сотрудника. Пожалуйста, попробуйте позже.",
            parse_mode="Markdown",
        )
    finally:
        await state.clear()
        logging.info(
            f"Состояние FSM удаления сотрудника очищено для админа {admin_user_id} после подтверждения."
        )

    await query.answer("Сотрудник удален.", show_alert=False)


@router.callback_query(
    AdminEmployeeStates.confirm_delete_employee,
    F.data == "admin_cancel_delete_employee",
)
async def admin_cancel_delete_employee(query: CallbackQuery, state: FSMContext):
    """
    Обрабатывает отмену удаления сотрудника админом в состоянии подтверждения удаления.
    Очищает состояние FSM и сообщает об отмене.
    """
    admin_user_id = query.from_user.id
    logging.info(f"Админ {admin_user_id} отменил удаление сотрудника.")

    await state.clear()
    logging.info(
        f"Состояние FSM удаления сотрудника очищено после отмены для админа {admin_user_id}."
    )

    await query.message.edit_text("Отмена удаления сотрудника.", reply_markup=None)

    await query.answer("Удаление отменено.", show_alert=False)


@router.callback_query(
    AdminEmployeeStates.waiting_for_employee_edit_choice,
    F.data == "admin_cancel_edit_employee",
)
async def admin_cancel_employee_edit(query: CallbackQuery, state: FSMContext):
    """
    Обрабатывает отмену редактирования сотрудника админом из состояния выбора поля.
    Очищает состояние FSM и сообщает об отмене.
    """
    admin_user_id = query.from_user.id
    logging.info(
        f"Админ {admin_user_id} отменил редактирование сотрудника из состояния выбора поля."
    )

    await state.clear()
    logging.info(
        f"Состояние FSM редактирования сотрудника очищено после отмены для админа {admin_user_id}."
    )

    await query.message.edit_text(
        "Отмена редактирования сотрудника.", reply_markup=None
    )

    await query.answer("Редактирование отменено.", show_alert=False)


@router.callback_query(
    AdminEmployeeStates.waiting_for_employee_edit_choice,
    F.data.startswith("admin_edit_employee_field_"),
)
async def admin_choose_employee_field_to_edit(query: CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор поля сотрудника ('Имя' или 'Специальность') для редактирования админом.
    Переводит в соответствующее состояние ожидания нового значения и запрашивает его.
    """
    admin_user_id = query.from_user.id
    try:
        parts = query.data.split("_")
        if len(parts) != 5:
            raise ValueError("Invalid callback data format.")
        field_name = parts[4]

        if field_name not in ["name", "specialty"]:
            raise ValueError(f"Unknown field name: {field_name}")

    except ValueError as e:
        logging.warning(
            f"Админ {admin_user_id} получил неверный формат callback data или неизвестное поле для редактирования сотрудника: '{query.data}'. Ошибка: {e}"
        )
        await query.answer(
            "Неизвестное поле для редактирования. Пожалуйста, выберите из списка.",
            show_alert=True,
        )
        return

    logging.info(
        f"Админ {admin_user_id} выбрал поле '{field_name}' для редактирования сотрудника."
    )

    data = await state.get_data()
    editing_employee_id = data.get("editing_employee_id")

    if editing_employee_id is None:
        logging.error(
            f"Ошибка FSM: ID сотрудника для редактирования не найден в контексте для админа {admin_user_id} в состоянии waiting_for_employee_edit_choice."
        )
        await query.answer(
            "Произошла ошибка. ID сотрудника не найден. Пожалуйста, начните редактирование заново.",
            show_alert=True,
        )
        await state.clear()
        await query.message.edit_text(
            "Произошла внутренняя ошибка. Пожалуйста, начните снова.", reply_markup=None
        )
        return

    prompt_message = ""
    next_state = None

    if field_name == "name":
        prompt_message = (
            "✏️ **Редактирование имени сотрудника.**\n\nВведите новое имя сотрудника:"
        )
        next_state = AdminEmployeeStates.waiting_for_new_employee_name
    elif field_name == "specialty":
        prompt_message = "🧑‍⚕️ **Редактирование специальности сотрудника.**\n\nВведите новую специальность сотрудника (можно пропустить, написав '-'):"
        next_state = AdminEmployeeStates.waiting_for_new_employee_specialty

    try:
        await query.message.edit_text(prompt_message, parse_mode="Markdown")
        await state.set_state(next_state)
        logging.info(
            f"Админ {admin_user_id} переведен в состояние {next_state} для ввода нового значения поля '{field_name}'."
        )
        await query.answer(
            f"Ожидаю новое значение для поля '{field_name}'.", show_alert=False
        )

    except Exception as e:
        logging.error(
            f"Ошибка при переходе в состояние ввода нового значения для админа {admin_user_id}: {e}"
        )
        await query.answer(
            "Произошла ошибка при переходе к вводу данных.", show_alert=True
        )
        await state.clear()
        await query.message.edit_text(
            "Произошла внутренняя ошибка. Пожалуйста, начните снова.", reply_markup=None
        )


@router.message(AdminEmployeeStates.waiting_for_new_employee_name, F.text)
async def process_admin_new_employee_name(message: Message, state: FSMContext):
    """
    Обрабатывает ввод нового имени сотрудника админом в состоянии AdminEmployeeStates.waiting_for_new_employee_name.
    Сохраняет новое имя в БД и сообщает результат.
    """
    admin_user_id = message.from_user.id
    new_name = message.text.strip()

    logging.info(
        f"Админ {admin_user_id} ввел новое имя сотрудника для редактирования: '{new_name}'."
    )

    if not new_name:
        await message.answer(
            "Имя сотрудника не может быть пустым. Пожалуйста, введите новое имя:"
        )
        return

    data = await state.get_data()
    editing_employee_id = data.get("editing_employee_id")

    if editing_employee_id is None:
        logging.error(
            f"Ошибка FSM: ID сотрудника для редактирования не найден в контексте для админа {admin_user_id} при вводе нового имени."
        )
        await message.answer(
            "Произошла ошибка при редактировании сотрудника. ID сотрудника не найден."
        )
        await state.clear()
        return

    updated = False
    try:
        async with async_session_factory() as session:
            employee_repo = EmployeeRepository(session)
            employee_service = EmployeeService(employee_repo)

            updates = {"name": new_name}
            updated = await employee_service.update_employee(
                editing_employee_id, updates
            )

        if updated:
            logging.info(
                f"Имя сотрудника ID={editing_employee_id} успешно обновлено на '{new_name}' админом {admin_user_id}."
            )
            await message.answer(
                f"✅ Имя сотрудника ID=`{editing_employee_id}` успешно обновлено на: **{new_name}**",
                parse_mode="Markdown",
            )
        else:
            logging.warning(
                f"Не удалось обновить имя сотрудника ID={editing_employee_id} на '{new_name}' (админ {admin_user_id})."
            )
            await message.answer(
                f"❌ Не удалось обновить имя сотрудника ID=`{editing_employee_id}`. Возможно, сотрудник не найден.",
                parse_mode="Markdown",
            )

    except Exception as e:
        logging.error(
            f"Критическая ошибка при обновлении имени сотрудника ID={editing_employee_id} админом {admin_user_id}: {e}"
        )
        await message.answer(
            "Произошла ошибка при сохранении нового имени сотрудника. Пожалуйста, попробуйте еще раз.",
            parse_mode="Markdown",
        )
    finally:
        await state.clear()
        logging.info(
            f"Состояние FSM редактирования сотрудника очищено после ввода имени для админа {admin_user_id}."
        )


@router.message(AdminEmployeeStates.waiting_for_new_employee_specialty, F.text)
async def process_admin_new_employee_specialty(message: Message, state: FSMContext):
    """
    Обрабатывает ввод новой специальности сотрудника админом в состоянии AdminEmployeeStates.waiting_for_new_employee_specialty.
    Сохраняет новую специальность в БД (или None) и сообщает результат.
    """
    admin_user_id = message.from_user.id
    new_specialty_input = message.text.strip()

    logging.info(
        f"Админ {admin_user_id} ввел новую специальность сотрудника для редактирования: '{new_specialty_input}'."
    )

    new_specialty = None

    if new_specialty_input != "-":
        new_specialty = new_specialty_input

    data = await state.get_data()
    editing_employee_id = data.get("editing_employee_id")

    if editing_employee_id is None:
        logging.error(
            f"Ошибка FSM: ID сотрудника для редактирования не найден в контексте для админа {admin_user_id} при вводе новой специальности."
        )
        await message.answer(
            "Произошла ошибка при редактировании сотрудника. ID сотрудника не найден."
        )
        await state.clear()
        return

    updated = False
    try:
        async with async_session_factory() as session:
            employee_repo = EmployeeRepository(session)
            employee_service = EmployeeService(employee_repo)

            updates = {"specialty": new_specialty}
            updated = await employee_service.update_employee(
                editing_employee_id, updates
            )

        if updated:
            logging.info(
                f"Специальность сотрудника ID={editing_employee_id} успешно обновлена на '{new_specialty}' админом {admin_user_id}."
            )
            await message.answer(
                f"✅ Специальность сотрудника ID=`{editing_employee_id}` успешно обновлена на: **{new_specialty if new_specialty else 'Не указана'}**",
                parse_mode="Markdown",
            )
        else:
            logging.warning(
                f"Не удалось обновить специальность сотрудника ID={editing_employee_id} на '{new_specialty}' (админ {admin_user_id})."
            )
            await message.answer(
                f"❌ Не удалось обновить специальность сотрудника ID=`{editing_employee_id}`. Возможно, сотрудник не найден.",
                parse_mode="Markdown",
            )

    except Exception as e:
        logging.error(
            f"Критическая ошибка при обновлении специальности сотрудника ID={editing_employee_id} админом {admin_user_id}: {e}"
        )
        await message.answer(
            "Произошла ошибка при сохранении новой специальности сотрудника. Пожалуйста, попробуйте еще раз.",
            parse_mode="Markdown",
        )
    finally:
        await state.clear()
        logging.info(
            f"Состояние FSM редактирования сотрудника очищено после ввода специальности для админа {admin_user_id}."
        )


@router.message(Command("admin_set_service_duration"))
async def admin_set_service_duration_cmd(message: Message):
    """
    Установить длительность услуги.
    """
    args = message.text.split()
    if len(args) != 3:
        await message.answer(
            "Использование: /admin_set_service_duration <ID услуги> <длительность в минутах>"
        )
        return

    service_id, duration = int(args[1]), int(args[2])

    async with async_session_factory() as session:
        service_repo = ServiceRepository(session)
        await service_repo.update_service(service_id, duration)

    await message.answer(
        f"Длительность услуги ID {service_id} установлена на {duration} минут."
    )


@router.message(Command("admin_edit_schedule"))
async def admin_edit_schedule_cmd(message: Message, state: FSMContext):
    """
    Показывает список сотрудников для выбора, чей график нужно редактировать.
    """
    async with async_session_factory() as session:
        result = await session.execute(select(Employee).order_by(Employee.name))
        employees = result.scalars().all()

    if not employees:
        await message.answer("В базе нет сотрудников.")
        return

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=emp.name)] for emp in employees],
        resize_keyboard=True,
    )
    await message.answer(
        "Выберите сотрудника для редактирования графика:", reply_markup=kb
    )
    await state.set_state("waiting_for_employee_schedule_edit")


@router.message(StateFilter("waiting_for_employee_schedule_edit"))
async def process_employee_schedule_edit_choice(message: Message, state: FSMContext):
    employee_name = message.text.strip()
    async with async_session_factory() as session:
        result = await session.execute(
            select(Employee).where(Employee.name == employee_name)
        )
        employee = result.scalars().first()
        if not employee:
            await message.answer("Сотрудник не найден. Попробуйте ещё раз.")
            return

        schedule_result = await session.execute(
            select(EmployeeSchedule)
            .where(EmployeeSchedule.employee_id == employee.id)
            .order_by(EmployeeSchedule.weekday, EmployeeSchedule.start_time)
        )
        schedule = schedule_result.scalars().all()

        await state.update_data(employee_id=employee.id)

        if schedule:
            schedule_text = "Текущий график:\n"
            days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
            for s in schedule:
                schedule_text += f"{days[s.weekday]}: {s.start_time} — {s.end_time}\n"
        else:
            schedule_text = "График не задан."

        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Добавить интервал")],
                [KeyboardButton(text="Удалить интервал")],
                [KeyboardButton(text="Назад")],
            ],
            resize_keyboard=True,
        )

        await message.answer(
            f"Вы выбрали сотрудника: {employee.name}\n\n"
            f"{schedule_text}\n\n"
            "Выберите действие:",
            reply_markup=kb,
        )
        await state.set_state("waiting_for_schedule_action")


@router.message(
    StateFilter("waiting_for_schedule_action"), F.text == "Добавить интервал"
)
async def admin_add_schedule_interval(message: Message, state: FSMContext):
    await message.answer(
        "Введите интервал в формате:\n\n"
        "`день недели HH:MM-HH:MM`\n\n"
        "Например: `1 09:00-18:00` (1 — понедельник, 7 — воскресенье)",
        parse_mode="Markdown",
    )
    await state.set_state("waiting_for_schedule_interval_input")


@router.message(StateFilter("waiting_for_schedule_interval_input"))
async def process_schedule_interval_input(message: Message, state: FSMContext):
    text = message.text.strip()
    if text.lower() == "назад":
        await state.clear()
        await message.answer(
            "Вы вышли из режима редактирования графика.", reply_markup=None
        )
        return
    try:
        parts = text.split()
        if len(parts) != 2:
            raise ValueError
        weekday = int(parts[0]) - 1
        time_range = parts[1].split("-")
        if len(time_range) != 2:
            raise ValueError
        start_time, end_time = time_range
        assert len(start_time) == 5 and len(end_time) == 5
    except Exception:
        await message.answer(
            "Неверный формат. Введите, например: `1 09:00-18:00`", parse_mode="Markdown"
        )
        return

    data = await state.get_data()
    employee_id = data.get("employee_id")
    if not employee_id:
        await message.answer("Ошибка: сотрудник не выбран.")
        await state.clear()
        return

    async with async_session_factory() as session:
        schedule = EmployeeSchedule(
            employee_id=employee_id,
            weekday=weekday,
            start_time=start_time,
            end_time=end_time,
        )
        session.add(schedule)
        await session.commit()

    await message.answer(
        "Интервал добавлен! Чтобы добавить ещё — отправьте новый интервал, или нажмите 'Назад'."
    )


@router.message(StateFilter("waiting_for_schedule_action"), F.text == "Назад")
@router.message(StateFilter("waiting_for_schedule_interval_input"), F.text == "Назад")
async def admin_schedule_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Вы вышли из режима редактирования графика.", reply_markup=None
    )


@router.message(Command("delete"))
async def admin_delete_booking_cmd(message: Message):
    args = message.text.strip().split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Используйте: /delete <ID записи>")
        return

    booking_id = int(args[1])
    try:
        async with async_session_factory() as session:
            booking_repo = BookingRepository(session)
            user_repo = UserRepository(session)
            service_repo = ServiceRepository(session)
            booking_service = BookingService(booking_repo, user_repo, service_repo)
            deleted = await booking_service.delete_booking(booking_id)
        if deleted:
            await message.answer(f"✅ Запись с ID {booking_id} успешно удалена.")
        else:
            await message.answer(f"❌ Запись с ID {booking_id} не найдена.")
    except Exception as e:
        logging.error(f"Ошибка при удалении записи ID={booking_id}: {e}")
        await message.answer("Произошла ошибка при удалении записи.")


@router.message(Command("admin_exit"))
async def admin_exit_cmd(message: Message, state: FSMContext):
    """
    Позволяет админу выйти из админ-меню и вернуться к пользовательской клавиатуре.
    """
    await state.clear()
    await message.answer(
        "Вы вышли из админ-меню. Возвращаю основное меню пользователя.",
        reply_markup=main_menu_kb(),
    )


@router.message(Command("admin_edit_contacts"))
async def admin_edit_contacts_cmd(message: Message, state: FSMContext):
    """
    Показывает текущие контакты и предлагает изменить.
    """
    async with async_session_factory() as session:
        from repositories.contacts_repo import ContactsRepository
        from services.contacts_service import ContactsService

        repo = ContactsRepository(session)
        service = ContactsService(repo)
        contacts = await service.get_contacts()
        if not contacts:
            contacts = Contacts(address="", about="", phone="", email="", map_url="")
            session.add(contacts)
            await session.commit()
        text = (
            f"Текущие контакты:\n"
            f"Адрес: {contacts.address}\n"
            f"О нас: {contacts.about}\n"
            f"Телефон: {contacts.phone}\n"
            f"Email: {contacts.email}\n"
            f"Карта: {contacts.map_url}\n\n"
            "Что хотите изменить? (отправьте: адрес/о нас/телефон/email/карта)"
        )
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Адрес")],
                [KeyboardButton(text="О нас")],
                [KeyboardButton(text="Телефон")],
                [KeyboardButton(text="Email")],
                [KeyboardButton(text="Карта")],
                [KeyboardButton(text="Отмена")],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await message.answer(text, reply_markup=kb)
        await state.set_state("waiting_for_contact_field")


@router.message(StateFilter("waiting_for_contact_field"), F.text)
async def admin_choose_contact_field(message: Message, state: FSMContext):
    """
    Обрабатывает выбор поля контактной информации для редактирования.
    Показывает пользователю приглашение ввести новое значение выбранного поля.
    """
    field = message.text.strip().lower()
    fields = {
        "адрес": "address",
        "о нас": "about",
        "телефон": "phone",
        "email": "email",
        "карта": "map_url",
    }
    if field == "отмена":
        await state.clear()
        await message.answer("Редактирование отменено.", reply_markup=None)
        return
    if field not in fields:
        await message.answer("Пожалуйста, выберите поле из меню.")
        return
    await state.update_data(contact_field=fields[field])
    await message.answer(
        f"Введите новое значение для поля '{field}':", reply_markup=None
    )
    await state.set_state("waiting_for_contact_value")


@router.message(StateFilter("waiting_for_contact_value"), F.text)
async def admin_set_contact_value(message: Message, state: FSMContext):
    value = message.text.strip()
    data = await state.get_data()
    field = data.get("contact_field")
    async with async_session_factory() as session:
        from repositories.contacts_repo import ContactsRepository
        from services.contacts_service import ContactsService

        repo = ContactsRepository(session)
        service = ContactsService(repo)
        await service.update_contacts(**{field: value})
    await message.answer("Контактная информация обновлена.")
    await state.clear()


@router.message(Command("chat_list"), F.from_user.id.in_(config.ADMIN_IDS))
async def show_chat_list(message: Message):
    """Показывает список активных чатов для админа"""
    try:
        async with async_session_factory() as session:
            message_repo = MessageRepository(session)
            users_with_messages = await message_repo.get_users_with_unread_messages()

            if not users_with_messages:
                await message.answer("Нет активных чатов с непрочитанными сообщениями.")
                return

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=f"💬 {user.name or f'User {user.telegram_id}'} ({count} сообщ.)",
                            callback_data=f"open_chat_{user.telegram_id}",
                        )
                    ]
                    for user, count in users_with_messages
                ]
            )
            await message.answer("Выберите чат для просмотра:", reply_markup=kb)

    except Exception as e:
        logging.error(f"Ошибка при получении списка чатов: {e}")
        await message.answer("Произошла ошибка при получении списка чатов.")


@router.callback_query(
    F.data.startswith("open_chat_"), F.from_user.id.in_(config.ADMIN_IDS)
)
async def open_chat(query: CallbackQuery, state: FSMContext):
    """Открывает чат с конкретным пользователем"""
    user_id = int(query.data.split("_")[2])

    try:
        async with async_session_factory() as session:
            message_repo = MessageRepository(session)
            messages = await message_repo.get_user_messages(user_id, limit=10)

            chat_text = "История сообщений:\n\n"
            for msg in messages:
                prefix = "👤" if not msg.is_from_admin else "👨‍💼"
                chat_text += f"{prefix} {msg.message_text}\n"

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Ответить", callback_data=f"reply_to_{user_id}"
                        )
                    ]
                ]
            )
            await query.message.edit_text(chat_text, reply_markup=kb)

    except Exception as e:
        logging.error(f"Ошибка при открытии чата с пользователем {user_id}: {e}")
        await query.answer("Ошибка при открытии чата", show_alert=True)


@router.callback_query(
    F.data.startswith("reply_to_"), F.from_user.id.in_(config.ADMIN_IDS)
)
async def start_admin_reply(query: CallbackQuery, state: FSMContext):
    """Начало ответа администратора пользователю"""
    user_id = int(query.data.split("_")[2])

    await state.update_data(reply_to_user_id=user_id)
    await state.set_state(ChatStates.admin_replying)

    await query.message.edit_text(
        f"Введите ваш ответ для пользователя {user_id}.\n"
        "Вы можете отправить текст или фото.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отменить ответ", callback_data="cancel_admin_reply"
                    )
                ]
            ]
        ),
    )
    await query.answer()


@router.message(ChatStates.admin_replying, F.content_type.in_({"text", "photo"}))
async def handle_admin_reply(message: Message, state: FSMContext):
    """Обработка ответа администратора"""
    data = await state.get_data()
    user_id = data.get("reply_to_user_id")

    if not user_id:
        await message.answer("Ошибка: не найден получатель сообщения")
        await state.clear()
        return

    try:
        async with async_session_factory() as session:
            message_repo = MessageRepository(session)

            if message.content_type == "text":
                await message_repo.create_message(
                    user_telegram_id=user_id,
                    message_text=message.text,
                    is_from_admin=True,
                    admin_telegram_id=message.from_user.id,
                )

                await message.bot.send_message(
                    user_id, f"Ответ администратора:\n{message.text}"
                )

            elif message.content_type == "photo":
                photo_file_id = message.photo[-1].file_id
                caption = message.caption or "Фото от администратора"

                await message_repo.create_message(
                    user_telegram_id=user_id,
                    message_text=caption,
                    is_from_admin=True,
                    attachment_id=photo_file_id,
                    admin_telegram_id=message.from_user.id,
                )

                await message.bot.send_photo(
                    user_id, photo_file_id, caption=f"Ответ администратора:\n{caption}"
                )

            await message.answer(f"✅ Ваш ответ отправлен пользователю {user_id}")

            users_with_messages = await message_repo.get_users_with_unread_messages()
            if users_with_messages:
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=f"💬 {user.name or f'User {user.telegram_id}'} ({count} сообщ.)",
                                callback_data=f"open_chat_{user.telegram_id}",
                            )
                        ]
                        for user, count in users_with_messages
                    ]
                )
                await message.answer("Активные чаты:", reply_markup=kb)
            else:
                await message.answer("Нет активных чатов с непрочитанными сообщениями.")

    except Exception as e:
        logging.error(
            f"Ошибка при отправке ответа администратора пользователю {user_id}: {e}"
        )
        await message.answer("❌ Произошла ошибка при отправке ответа.")
    finally:
        await state.clear()


@router.callback_query(F.data == "cancel_admin_reply")
async def cancel_admin_reply(query: CallbackQuery, state: FSMContext):
    """Отмена ответа администратора"""
    await state.clear()
    await query.message.edit_text("Ответ отменен")
    await query.answer()
