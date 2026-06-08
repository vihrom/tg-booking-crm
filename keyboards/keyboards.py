import calendar
import logging
from datetime import date, datetime, time

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from models.models import Booking, Employee, Service


def main_menu_kb() -> ReplyKeyboardMarkup:
    """Создание клавиатуры главного меню"""
    kb = [
        [KeyboardButton(text="📝 Записаться")],
        [KeyboardButton(text="🗓 Мои записи"), KeyboardButton(text="💸 Цены")],
        [KeyboardButton(text="👤 Мой профиль")],
        [KeyboardButton(text="📍 Контакты")],
        [KeyboardButton(text="❓ Помощь")],
        [KeyboardButton(text="💬 Чат с администратором")],
        [KeyboardButton(text="💎 Моя лояльность")],
    ]
    keyboard = ReplyKeyboardMarkup(
        keyboard=kb, resize_keyboard=True, one_time_keyboard=False
    )
    return keyboard


def create_time_keyboard(
    selected_date: date, booked_time_strings: list[str]
) -> InlineKeyboardMarkup | None:
    """
    Создает inline клавиатуру с доступными временными слотами для выбранной даты.
    Исключает слоты, указанные в booked_time_strings.
    Возвращает InlineKeyboardMarkup или None, если нет доступных слотов.
    """
    buttons = []
    start_time_minutes = 9 * 60  # 9:00 в минутах
    end_time_minutes = 18 * 60  # 18:00 в минутах
    interval_minutes = 30

    now = datetime.now()
    today = date.today()

    all_potential_slots = []
    for total_minutes in range(
        start_time_minutes, end_time_minutes + 1, interval_minutes
    ):
        hours = total_minutes // 60
        minutes = total_minutes % 60
        time_obj = time(hours, minutes)
        time_str = time_obj.strftime("%H:%M")

        slot_datetime = datetime.combine(selected_date, time_obj)

        if selected_date > today or (selected_date == today and slot_datetime > now):
            all_potential_slots.append(time_str)

    available_slots = [
        slot for slot in all_potential_slots if slot not in booked_time_strings
    ]

    if not available_slots:
        return None

    for time_str in available_slots:
        callback_data = f"time_{time_str}"
        buttons.append(InlineKeyboardButton(text=time_str, callback_data=callback_data))

    keyboard_rows = []
    row = []
    for button in buttons:
        row.append(button)
        if len(row) == 4:
            keyboard_rows.append(row)
            row = []
    if row:
        keyboard_rows.append(row)

    keyboard_rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад к дате", callback_data="back_to_date_selection"
            )
        ]
    )
    keyboard_rows.append(
        [
            InlineKeyboardButton(
                text="❌ Отменить запись", callback_data="cancel_fsm_process"
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


def create_my_bookings_keyboard(bookings: list[Booking]) -> InlineKeyboardMarkup:
    """
    Создает inline клавиатуру со списком записей пользователя
    и кнопкой отмены для каждой записи.
    """
    keyboard_rows = []
    for booking in bookings:
        button_text = f"🗓 {booking.datetime.strftime('%d.%m %H:%M')} (ID: {booking.id})"
        details_callback_data = f"booking_details_{booking.id}"
        cancel_callback_data = f"cancel_booking_{booking.id}"

        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    text=button_text, callback_data=details_callback_data
                ),
                InlineKeyboardButton(
                    text="❌ Отменить", callback_data=cancel_callback_data
                ),
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


def create_service_selection_keyboard(services: list[Service]) -> InlineKeyboardMarkup:
    """
    Создает inline клавиатуру для выбора услуги из списка.
    """
    buttons = []

    for service in services:
        callback_data = f"select_service_{service.id}"
        button_text = f"{service.name}"
        if service.price:
            button_text += f" ({service.price})"

        buttons.append(
            InlineKeyboardButton(text=button_text, callback_data=callback_data)
        )

    keyboard_rows = [[btn] for btn in buttons]

    keyboard_rows.append(
        [
            InlineKeyboardButton(
                text="❌ Отменить запись", callback_data="cancel_fsm_process"
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


def create_employee_selection_keyboard(
    employees: list[Employee],
) -> InlineKeyboardMarkup:
    """
    Создает inline клавиатуру для выбора сотрудника из списка.
    """
    buttons = []

    for employee in employees:
        callback_data = f"select_employee_{employee.id}"
        button_text = f"{employee.name}"
        if employee.specialty:
            button_text += f" ({employee.specialty})"

        buttons.append(
            InlineKeyboardButton(text=button_text, callback_data=callback_data)
        )

    keyboard_rows = [[btn] for btn in buttons]

    keyboard_rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад к услугам", callback_data="back_to_service_selection"
            )
        ]
    )
    keyboard_rows.append(
        [
            InlineKeyboardButton(
                text="❌ Отменить запись", callback_data="cancel_fsm_process"
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


def create_admin_service_management_keyboard(
    services: list[Service],
) -> InlineKeyboardMarkup | None:
    """
    Создает inline клавиатуру со списком услуг и кнопками 'Изменить' и 'Удалить' для админа.
    Каждая услуга представлена в отдельной строке с ее названием и двумя кнопками.
    """
    if not services:
        return None

    keyboard_rows = []

    for service in services:
        row = [
            InlineKeyboardButton(
                text=service.name, callback_data=f"admin_service_info_{service.id}"
            ),
            InlineKeyboardButton(
                text="✏️ Изменить", callback_data=f"admin_edit_service_{service.id}"
            ),
            InlineKeyboardButton(
                text="🗑️ Удалить", callback_data=f"admin_delete_service_{service.id}"
            ),
        ]
        keyboard_rows.append(row)

    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


def create_admin_employee_association_keyboard(
    employees: list[Employee],
) -> InlineKeyboardMarkup | None:
    """
    Создает inline клавиатуру со списком сотрудников для выбора управления их услугами.
    """
    if not employees:
        return None

    keyboard_rows = []

    for employee in employees:
        row = [
            InlineKeyboardButton(
                text=f"{employee.name} ({employee.specialty if employee.specialty else 'Не указана'})",
                callback_data=f"admin_manage_employee_services_{employee.id}",  # <-- Callback для выбора сотрудника
            )
        ]
        keyboard_rows.append(row)

    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


def create_employee_service_toggle_keyboard(
    all_services: list[Service], employee_services_ids: set[int], employee_id: int
) -> InlineKeyboardMarkup | None:
    """
    Создает inline клавиатуру со списком ВСЕХ услуг и кнопками-переключателями для связи с определенным сотрудником.
    employee_services_ids - сет с ID услуг, которые УЖЕ связаны с сотрудником.
    employee_id - ID сотрудника, для которого формируется клавиатура.
    """
    if not all_services:
        return None

    keyboard_rows = []

    for service in all_services:
        is_associated = service.id in employee_services_ids

        button_text = f"{'✅' if is_associated else '⬜'} {service.name}"

        callback_data = f"admin_toggle_association_{employee_id}_{service.id}"  # <-- Callback для переключения

        row = [InlineKeyboardButton(text=button_text, callback_data=callback_data)]
        keyboard_rows.append(row)

    keyboard_rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Готово", callback_data="admin_done_managing_services"
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


def create_admin_employee_management_keyboard(
    employees: list[Employee],
) -> InlineKeyboardMarkup | None:
    """
    Создает inline клавиатуру со списком сотрудников и кнопками 'Изменить' и 'Удалить' для админа.
    Каждый сотрудник представлен в отдельной строке с его именем/специальностью и двумя кнопками.
    """
    if not employees:
        return None

    seen_employee_names = set()

    for employee in employees:
        if employee.name in seen_employee_names:
            logging.warning(
                f"Пропускаем сотрудника с дублирующимся именем '{employee.name}' (ID: {employee.id}) при создании клавиатуры управления сотрудниками."
            )
            continue

        seen_employee_names.add(employee.name)
