import asyncio
import logging

from kzkitty.bot import bot

logger = logging.getLogger('kzkitty')

if __name__ == '__main__':
    try:
        import uvloop
    except ImportError:
        pass
    else:
        loop = uvloop.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.info('Installed uvloop event loop')

    bot.run()
