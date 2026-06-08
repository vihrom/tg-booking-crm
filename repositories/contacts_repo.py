from sqlalchemy import select, update

from models.models import Contacts


class ContactsRepository:
    def __init__(self, session):
        self.session = session

    async def get_contacts(self):
        result = await self.session.execute(select(Contacts))
        return result.scalar_one_or_none()

    async def update_contacts(self, **kwargs):
        await self.session.execute(update(Contacts).values(**kwargs))
        await self.session.commit()
