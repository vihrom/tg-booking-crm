class ContactsService:
    def __init__(self, repo):
        self.repo = repo

    async def get_contacts(self):
        return await self.repo.get_contacts()

    async def update_contacts(self, **kwargs):
        return await self.repo.update_contacts(**kwargs)
