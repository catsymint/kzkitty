import csv
import logging
import os

import hikari
from tortoise import Tortoise

from kzkitty.models import Mode, User

logger = logging.getLogger('kzkitty.gateway')

class GatewayBot(hikari.GatewayBot):
    async def start(self, *args, **kwargs) -> None:
        await Tortoise.init(
            db_url='sqlite://kzkitty.db',
            modules={'models': ['kzkitty.models']},
        )
        await Tortoise.generate_schemas()

        initial_user_file = os.environ.get('KZKITTY_INITIAL_USERS')
        if initial_user_file is not None:
            if await User.all().count() == 0:
                users = []
                with open(initial_user_file, newline='') as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        users.append(User(id=int(row['id']),
                                          steamid64=int(row['steamid64']),
                                          mode=Mode(row['mode'])))
                await User.bulk_create(users)
                logger.info('Imported %d users from %s', len(users),
                            initial_user_file)

        await super().start(*args, **kwargs)

    async def close(self) -> None:
        await Tortoise.close_connections()
        await super().close()
