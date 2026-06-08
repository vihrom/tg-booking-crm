from datetime import date, datetime, time, timedelta
from calendar import monthrange


def get_free_slots(schedule_intervals, booked_intervals, service_duration, date_obj):
    """
    schedule_intervals: [('09:00', '13:00'), ...]
    booked_intervals: [(start, end), ...] где start/end могут быть строками ('10:00'), time или datetime
    service_duration: int (минуты)
    date_obj: date
    Возвращает список строк времени начала свободных слотов: ['09:00', '09:30', ...]
    """
    slots = []
    booked = []
    for start, end in booked_intervals:
        if isinstance(start, str):
            start_time = datetime.strptime(start, "%H:%M").time()
        elif isinstance(start, datetime):
            start_time = start.time()
        elif isinstance(start, time):
            start_time = start
        else:
            raise ValueError("Некорректный тип start в booked_intervals")

        if isinstance(end, str):
            end_time = datetime.strptime(end, "%H:%M").time()
        elif isinstance(end, datetime):
            end_time = end.time()
        elif isinstance(end, time):
            end_time = end
        else:
            raise ValueError("Некорректный тип end в booked_intervals")

        booked.append(
            (
                datetime.combine(date_obj, start_time),
                datetime.combine(date_obj, end_time),
            )
        )

    for interval_start, interval_end in schedule_intervals:
        start_dt = datetime.combine(
            date_obj, datetime.strptime(interval_start, "%H:%M").time()
        )
        end_dt = datetime.combine(
            date_obj, datetime.strptime(interval_end, "%H:%M").time()
        )
        slot = start_dt
        while slot + timedelta(minutes=service_duration) <= end_dt:
            slot_end = slot + timedelta(minutes=service_duration)
            # Проверяем, не пересекается ли с занятыми
            overlap = False
            for b_start, b_end in booked:
                if not (slot_end <= b_start or slot >= b_end):
                    overlap = True
                    break
            if not overlap:
                slots.append(slot.strftime("%H:%M"))
            slot += timedelta(minutes=30)  # шаг 30 минут
    return slots


async def get_available_days_for_employee(
    session, employee_id, service_id, year, month
):
    """
    Возвращает список дат (date), на которые есть хотя бы один свободный слот для сотрудника и услуги.
    """
    from repositories.employee_repo import EmployeeRepository
    from repositories.booking_repo import BookingRepository
    from repositories.service_repo import ServiceRepository
    from services.employee_service import EmployeeService
    from utils.slots import get_free_slots

    employee_repo = EmployeeRepository(session)
    employee_service = EmployeeService(employee_repo)
    booking_repo = BookingRepository(session)
    service_repo = ServiceRepository(session)

    num_days = monthrange(year, month)[1]
    available_days = []
    duration = await service_repo.get_service_duration(service_id)

    for day in range(1, num_days + 1):
        d = date(year, month, day)
        weekday = d.weekday()
        schedule_intervals = await employee_service.get_employee_schedule(
            employee_id, weekday
        )
        if not schedule_intervals:
            continue
        booked_intervals = await booking_repo.get_employee_bookings(employee_id, d)
        free_slots = get_free_slots(schedule_intervals, booked_intervals, duration, d)
        if free_slots:
            available_days.append(d)
    return available_days


def get_available_days_for_month(
    schedule_intervals, booked_intervals_by_day, service_duration, year, month
):
    """
    Возвращает список дат (date), на которые есть хотя бы один свободный слот.
    booked_intervals_by_day: dict[date, list[(start, end)]]
    """
    available_days = []
    num_days = monthrange(year, month)[1]
    for day in range(1, num_days + 1):
        d = date(year, month, day)
        booked = booked_intervals_by_day.get(d, [])
        free_slots = get_free_slots(schedule_intervals, booked, service_duration, d)
        if free_slots:
            available_days.append(d)
    return available_days
