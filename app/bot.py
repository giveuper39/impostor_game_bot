import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message) -> None:
    if message.chat.type == "private":
        await message.reply(
            f"Привет, {message.from_user.full_name}! Это наша личная переписка и сюда я буду скидывать твою роль и слово!"
        )
    elif message.chat.type == "group":
        await message.bot.send_message(message.chat.id, f"Всем привет, друзья! Давайте играть!")


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
