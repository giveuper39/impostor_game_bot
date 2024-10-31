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
from db import init_db, load_data_from_file
from dotenv import load_dotenv
from game_functions import get_imposters, get_random_order, select_word_theme
from collections import defaultdict

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
NUM_ROUNDS = 1

dp = Dispatcher(storage=MemoryStorage(), fsm_strategy=FSMStrategy.CHAT)
router = Router()
players: dict[int, str] = {}
votes = defaultdict(int)
voted: list[int] = []


class States(StatesGroup):
    WaitingForPlayers = State()
    SendingWords = State()
    WatchingAssoc = State()
    Voting = State()
    GameFinish = State()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    cur = await state.get_state()
    if cur is not None:
        return

    await state.set_state(None)
    if message.chat.type == "private":
        await message.reply(
            f"Привет, {message.from_user.full_name}! Это наша личная переписка и сюда я буду скидывать твою роль, тему и слово!",
        )
    elif message.chat.type == "group":
        result = await message.bot.get_chat_member_count(message.chat.id)
        await message.bot.send_message(
            message.chat.id,
            f"Всем привет, друзья! Давайте играть! Сейчас в группе {result - 1} людей и я:)\n"
            f"Чтобы начать игру отправьте команду /start_game <количество игроков> <количество импосторов> (по умолчанию, 4 игрока и 1 импостор)",
        )


@router.message(Command("exit"))
async def exit_from_game(message: Message, state: FSMContext) -> None:
    await state.set_state(None)
    await message.reply("Все остановлено")


@router.message(Command("startgame"))
async def start_game(message: Message, state: FSMContext, command: CommandObject) -> None:
    cur = await state.get_state()
    if cur is not None:
        return
    join_button = InlineKeyboardButton(text="Присоединиться", callback_data="join")
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[[join_button]])
    if message.chat.type == "private":
        await message.reply("Нельзя начать игру в приватном чате!")
    elif message.chat.type == "group":
        args = command.args
        if not args:
            player_num, imposter_num = 4, 1
        else:
            args = args.split()
            if len(args) != 2:
                return
            player_num, imposter_num = map(int, args)
        if imposter_num >= player_num:
            return

        session_data = {"player_num": player_num, "imposter_num": imposter_num}
        await state.set_state(States.WaitingForPlayers)
        head_id = message.from_user.id
        head = message.from_user.username
        players.clear()
        votes.clear()
        voted.clear()
        players[head_id] = head
        await message.reply(
            "Если вы хотите присоединиться к игре, нажмите на кнопку 'Присоединиться'.",
            reply_markup=reply_markup,
        )
        msg = await message.bot.send_message(
            message.chat.id,
            f"Текущее количество игроков: {len(players)}/{player_num}\nИграют: {', '.join(players.values())}",
        )
        session_data["head"] = head
        session_data["msg_id"] = msg.message_id
        session_data["chat_id"] = msg.chat.id

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
            f"Все игроки в сборе. Количество импостеров - {data['imposter_num']}. Отправляю слова и темы!",
        )
        await send_words_to_players(msg, state)


async def send_words_to_players(message: Message, state: FSMContext) -> None:
    chat_name = message.chat.title
    word, theme = select_word_theme()
    data = (await state.get_data())["session_data"]
    imposters = get_imposters(list(players.keys()), data["imposter_num"])
    order = get_random_order(list(players.keys()))
    data["imposters"] = imposters
    data["order"] = order
    data["word"] = word
    data["current_player"] = 0
    data["current_round"] = 1
    chat_id = data["chat_id"]

    for p_id in players:
        if p_id not in imposters:
            await message.bot.send_message(p_id, f"Вы получаете слово {word} (тема - {theme}) из чата {chat_name}!")
        else:
            await message.bot.send_message(p_id, f"Вы предатель!!! Тема - {theme}, удачи:)")

    await message.bot.send_message(
        chat_id,
        "Я отправил каждому игроку сообщение с его ролью и словом. Чтобы написать ассоциацию в свой ход введите /assoc 'ассоциация'",
    )
    await message.bot.send_message(chat_id, f"Раунд: 1/{NUM_ROUNDS}.")
    await message.bot.send_message(chat_id, f"Ассоциацию называет {players[order[0]]}.")

    await state.update_data(session_data=data)
    await state.set_state(States.WatchingAssoc)


@router.message(Command("assoc"))
async def association_round(message: Message, state: FSMContext, command: CommandObject) -> None:
    cur = await state.get_state()
    if cur != States.WatchingAssoc.state:
        return

    data = (await state.get_data())["session_data"]
    current_round = data["current_round"]
    current_player = data["current_player"]
    player_num = data["player_num"]
    order = data["order"]
    if order[current_player] != message.from_user.id:
        await message.reply(f"Сейчас ход игрока: {players[order[current_player]]}")
        return

    if not command.args:
        await message.reply(f"Введите ассоциацию в формате '/assoc <ассоциация>'")
        return
    assoc = command.args
    if current_player == player_num - 1:
        current_round += 1
        if current_round == NUM_ROUNDS + 1:
            await state.set_state(States.Voting)
            await message.bot.send_message(
                message.chat.id,
                f"Игра закончилась, переходим к голосованию. "
                f"Кто же все-таки импостер? (голос импостера тоже учитывается, если импостер набрал одинаковое количество голосов с другим игроком, он побеждает",
            )
            await send_voting_message(message, state)
            return

        current_player = 0
        await message.bot.send_message(message.chat.id, f"Раунд: {current_round}/{NUM_ROUNDS}.")
        await message.bot.send_message(
            message.chat.id,
            f"{players[order[player_num - 1]]} сказал: {assoc}.\n" f"Ассоциацию называет: {players[order[0]]}",
        )
    else:
        await message.bot.send_message(
            message.chat.id,
            f"{players[order[current_player]]} сказал: {assoc}.\n"
            f"Ассоциацию называет: {players[order[current_player + 1]]}",
        )
        current_player += 1

    data["current_player"] = current_player
    data["current_round"] = current_round
    await state.update_data(session_data=data)


async def send_voting_message(message: Message, state: FSMContext) -> None:
    data = (await state.get_data())["session_data"]
    vote_button_arr = [InlineKeyboardButton(text=v, callback_data=f"vote{k}") for k, v in players.items()]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[vote_button_arr])
    await message.bot.send_message(message.chat.id, text="Проголосуйте за импостера", reply_markup=reply_markup)

    vote_str = "\n".join(f"{v}: 0" for v in players.values())
    msg = await message.bot.send_message(message.chat.id, f"Голоса:\n{vote_str}")
    data["msg_id"] = msg.message_id
    await state.update_data(session_data=data)


async def update_voting_message(message: Message, state: FSMContext) -> None:
    data = (await state.get_data())["session_data"]
    vote_str = "\n".join(f"{players[k]}: {votes[k]}" for k in players.keys())
    msg_id = data["msg_id"]
    await message.bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text=f"Голоса:\n{vote_str}")


@router.message(Command("vote"))
async def force_vote(message: Message, state: FSMContext) -> None:
    cur = await state.get_state()
    if cur != States.WatchingAssoc.state:
        return
    # TODO: доделать

    await send_voting_message(message, state)


@router.callback_query(F.data.startswith("vote"))
async def vote_for_imposter(callback: CallbackQuery, state: FSMContext) -> None:
    cur = await state.get_state()
    if cur != States.Voting.state:
        return

    voter_id = callback.from_user.id
    voted_id = int(callback.data[4:])
    if voter_id in voted or voter_id == voted_id:
        return

    votes[voted_id] += 1

    await update_voting_message(callback.message, state)

    if len(voted) == len(players):
        await state.set_state(States.GameFinish)


async def finish_game(message: Message, state: FSMContext) -> None:
    # TODO: доделать
    return


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    dp.include_router(router)
    init_db()
    load_data_from_file("example_words.txt")
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
