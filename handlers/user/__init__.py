from aiogram import Router
from .start import start_router

user_main_router = Router()

user_main_router.include_routers(start_router)
