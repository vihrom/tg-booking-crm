from datetime import datetime as dt_type

from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    select,
    update,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, mapped_column, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    phone: Mapped[str] = mapped_column(String, nullable=False)
    bookings = relationship("Booking", back_populates="user")
    admin_messages = relationship("AdminMessage", back_populates="user")
    loyalty = relationship("LoyaltyPoints", uselist=False, back_populates="user")

    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id}, name='{self.name}', phone='{self.phone}')>"


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    phone: Mapped[str] = mapped_column(String, nullable=False)
    datetime: Mapped[dt_type] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[dt_type | None] = mapped_column(DateTime, nullable=True)
    service_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("services.id"), nullable=False
    )
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id"), nullable=True
    )
    user_telegram_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=False
    )
    user = relationship("User", back_populates="bookings")
    __table_args__ = (
        UniqueConstraint(
            "datetime",
            "employee_id",
            "service_id",
            name="_datetime_employee_service_uc",
        ),
    )
    service = relationship("Service")
    employee = relationship("Employee")

    def __repr__(self):
        return f"<Booking(id={self.id}, name='{self.name}', phone='{self.phone}', datetime='{self.datetime}', user_telegram_id={self.user_telegram_id}, service_id={self.service_id}, employee_id={self.employee_id})>"


employee_service_association = Table(
    "employee_service_association",
    Base.metadata,
    Column("employee_id", Integer, ForeignKey("employees.id"), primary_key=True),
    Column("service_id", Integer, ForeignKey("services.id"), primary_key=True),
)


class Service(Base):
    __tablename__ = "services"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    price: Mapped[str] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    employees = relationship(
        "Employee", secondary=employee_service_association, back_populates="services"
    )

    def __repr__(self):
        return f"<Service(id={self.id}, name='{self.name}', price='{self.price}')>"


class EmployeeSchedule(Base):
    __tablename__ = "employee_schedule"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id"), nullable=False
    )
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[str] = mapped_column(String, nullable=False)
    end_time: Mapped[str] = mapped_column(String, nullable=False)
    employee = relationship("Employee", back_populates="schedules")


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    specialty: Mapped[str] = mapped_column(String, nullable=True)
    services = relationship(
        "Service", secondary=employee_service_association, back_populates="employees"
    )
    schedules = relationship("EmployeeSchedule", back_populates="employee")

    def __repr__(self):
        return f"<Employee(id={self.id}, name='{self.name}', specialty='{self.specialty}')>"


class Contacts(Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    address: Mapped[str]
    about: Mapped[str]
    phone: Mapped[str]
    email: Mapped[str]
    map_url: Mapped[str]


class ContactsRepository:
    def __init__(self, session):
        self.session = session

    async def get_contacts(self):
        result = await self.session.execute(select(Contacts))
        return result.scalar_one_or_none()

    async def update_contacts(self, **kwargs):
        await self.session.execute(update(Contacts).values(**kwargs))
        await self.session.commit()


class ContactsService:
    def __init__(self, repo):
        self.repo = repo

    async def get_contacts(self):
        return await self.repo.get_contacts()

    async def update_contacts(self, **kwargs):
        return await self.repo.update_contacts(**kwargs)


class BookingStates(StatesGroup):
    waiting_for_service = State()
    waiting_for_employee = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_confirmation = State()


class RegistrationStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()


class ProfileStates(StatesGroup):
    waiting_for_new_name = State()
    waiting_for_new_phone = State()


class AdminServiceStates(StatesGroup):
    waiting_for_service_name = State()
    waiting_for_service_price = State()
    waiting_for_service_description = State()
    waiting_for_service_duration = State()
    waiting_for_service_management_choice = State()
    waiting_for_edit_choice = State()
    waiting_for_new_service_name = State()
    waiting_for_new_service_price = State()
    waiting_for_new_service_description = State()
    waiting_for_service_to_delete = State()
    confirm_delete_service = State()


class AdminEmployeeStates(StatesGroup):
    waiting_for_employee_name = State()
    waiting_for_employee_specialty = State()
    waiting_for_employee_management_choice = State()
    waiting_for_employee_to_edit = State()
    waiting_for_employee_edit_choice = State()
    waiting_for_new_employee_name = State()
    waiting_for_new_employee_specialty = State()
    waiting_for_employee_to_delete = State()
    confirm_delete_employee = State()
    waiting_for_employee_for_association = State()
    waiting_for_service_association_choice = State()


class ChatStates(StatesGroup):
    in_chat = State()
    waiting_for_response = State()
    admin_replying = State()


class AdminMessage(Base):
    __tablename__ = "admin_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_telegram_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=False
    )
    admin_telegram_id: Mapped[int] = mapped_column(
        BigInteger, nullable=True
    )  # Add this line
    message_text: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[dt_type] = mapped_column(DateTime, default=dt_type.now)
    is_from_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    attachment_id: Mapped[str] = mapped_column(String, nullable=True)

    user = relationship("User", back_populates="admin_messages")


class LoyaltyPoints(Base):
    __tablename__ = "loyalty_points"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_telegram_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=False
    )
    points: Mapped[int] = mapped_column(Integer, default=0)
    total_spent: Mapped[float] = mapped_column(Float, default=0.0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    last_visit: Mapped[dt_type] = mapped_column(DateTime, nullable=True)

    user = relationship("User", back_populates="loyalty")
