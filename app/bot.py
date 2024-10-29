import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.strategy import FSMStrategy
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

dp = Dispatcher(storage=MemoryStorage(), fsm_strategy=FSMStrategy.CHAT)
router = Router()
players = {}
order = []


class States(StatesGroup):
    WaitingForPlayers = State()
    SendingWords = State()
    WatchingAssoc = State()
    Voting = State()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    cur = await state.get_state()
    if cur is not None:
        return

    await state.set_state(None)
    if message.chat.type == "private":
        await message.reply(f"Привет, {message.from_user.full_name}! Это наша личная переписка и сюда я буду скидывать твою роль, тему и слово!")
    elif message.chat.type == "group":
        result = await message.bot.get_chat_member_count(message.chat.id)
        await message.bot.send_message(
            message.chat.id,
            f"Всем привет, друзья! Давайте играть! Сейчас в группе {result - 1} людей и я:)\n"
            f"Чтобы начать игру отправьте команду /start_game <количество игроков> <количество импосторов> (по умолчанию, 4 игрока и 1 импостор)",
        )


@router.message(Command("start_game"))
async def start_game(message: Message, state: FSMContext, command: CommandObject) -> None:
    cur = await state.get_state()
    if cur is not None:
        return
    join_button = InlineKeyboardButton(text="Присоединиться", callback_data="join")
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[[join_button]])
    if message.chat.type == "private":
        await message.reply("Нельзя начать игру в приватном чате!")
    elif message.chat.type == "group":
        player_num, impostor_num = 4, 1
        args = command.args
        if args:
            player_num, impostor_num = map(int, args.split())

        if impostor_num >= player_num:
            return

        session_data = {"player_num": player_num, "impostor_num": impostor_num}
        await state.set_state(States.WaitingForPlayers)
        head_id = message.from_user.id
        head = message.from_user.username
        players.clear()
        players[head_id] = head
        await message.reply("Если вы хотите присоединиться к игре, нажмите на кнопку 'Присоединиться'.", reply_markup=reply_markup)
        msg = await message.bot.send_message(
            message.chat.id, f"Текущее количество игроков: {len(players)}/{player_num}\nИграют: {', '.join(players.values())}",
        )
        session_data["head"] = head
        session_data["msg_id"] = msg.message_id

        await state.update_data(session_data=session_data)


@router.callback_query(F.data == "join")
async def join_game(callback: CallbackQuery, state: FSMContext) -> None:
    cur = await state.get_state()
    if cur != States.WaitingForPlayers.state:
        return

    player_id = callback.from_user.id
    player_username = callback.from_user.username
    data = (await state.get_data())["session_data"]
    if player_id not in players:
        players[player_id] = player_username
        msg_id = data["msg_id"]
        await callback.message.bot.edit_message_text(
            f"Текущее количество игроков: {len(players)}/{data['player_num']}\nИграют: {', '.join(players.values())}",
            chat_id=callback.message.chat.id,
            message_id=msg_id,
        )
    if len(players) == data["player_num"]:
        await state.set_state(States.SendingWords)
        msg = await callback.message.bot.send_message(
            callback.message.chat.id,
            f"Все игроки в сборе. Количество импостеров - {data['impostor_num']}. Я отправил каждому игроку сообщение с его ролью и словом. Чтобы написать ассоциацию в свой ход введите /assoc 'ассоциация'",
        )
        await send_words_to_players(msg, state)


async def send_words_to_players(message: Message, state: FSMContext) -> None:
    chat_name = message.chat.title
    word = "asdadad"
    for p_id in players:
        msg = await message.bot.send_message(p_id, f"Вы получаете слово {word} из чата {chat_name}!")
    # TODO: сделать рандомный выбор импосторов, модель с темами и словами,

async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
