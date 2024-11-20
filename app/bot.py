import asyncio
import logging
import os
import sys

from aiogram.exceptions import TelegramForbiddenError
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
    BotCommand,
)
from certifi.core import exit_cacert_ctx

from db import init_db, load_data_from_file
from dotenv import load_dotenv
from game_functions import get_imposters, get_random_order, select_word_theme
from collections import defaultdict

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
NUM_ROUNDS = 3

dp = Dispatcher(storage=MemoryStorage(), fsm_strategy=FSMStrategy.CHAT)
router = Router()


class States(StatesGroup):
    WaitingForPlayers = State()
    SendingWords = State()
    WatchingAssoc = State()
    Voting = State()
    GameFinish = State()


async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="/start", description="Начать использование бота"),
        BotCommand(command="/exit", description="Прервать текущие действия и вернуться к началу"),
        BotCommand(command="/startgame", description="Начать игру (/startgame <кол-во игроков> <кол-во импостеров>)"),
        BotCommand(command="/vote", description="Начать голосование заранее."),
        BotCommand(command="/a", description="Ввести ассоциацию (/a <ассоциация>)"),
    ]
    await bot.set_my_commands(commands)


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    cur = await state.get_state()
    if cur is not None:
        return

    if message.chat.type == "private":
        await message.reply(
            f"Привет, {message.from_user.full_name}! Это наша личная переписка и сюда я буду скидывать твою роль, тему и слово!",
        )
    else:
        result = await message.bot.get_chat_member_count(message.chat.id)
        await message.bot.send_message(
            message.chat.id,
            f"Всем привет, друзья! Давайте играть! Сейчас в группе {result - 1} людей и я:)\n"
            f"Чтобы начать игру отправьте команду /startgame <количество игроков> (по умолчанию, 4 игрока)",
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
    else:
        args = command.args
        if not args:
            player_num = 4
        else:
            player_num = int(args)

        session_data = {"player_num": player_num}
        await state.set_state(States.WaitingForPlayers)
        head_id = message.from_user.id
        head = message.from_user.username
        players: dict[int, str] = {}
        votes = defaultdict(int)
        voted: list[int] = []
        players[head_id] = head
        await message.reply(
            "Если вы хотите присоединиться к игре, нажмите на кнопку 'Присоединиться'. "
            "Перед этим удостоверьтесь, что бот может написать вам в лс (для этого перейдите в диалог с ботом и нажмите 'Старт' или напишите /start)",
            reply_markup=reply_markup,
        )
        msg = await message.bot.send_message(
            message.chat.id,
            f"Текущее количество игроков: {len(players)}/{player_num}\nИграют: {', '.join(players.values())}",
        )
        session_data["head"] = head
        session_data["msg_id"] = msg.message_id
        session_data["chat_id"] = msg.chat.id
        session_data["players"] = players
        session_data["votes"] = votes
        session_data["voted"] = voted

        await state.update_data(session_data=session_data)


@router.callback_query(F.data == "join")
async def join_game(callback: CallbackQuery, state: FSMContext) -> None:
    cur = await state.get_state()
    if cur != States.WaitingForPlayers.state:
        return

    player_id = callback.from_user.id
    player_username = callback.from_user.username
    data = (await state.get_data())["session_data"]
    players = data["players"]
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
            f"Все игроки в сборе. Отправляю слова и темы!",
        )
        await send_words_to_players(msg, state)


async def send_words_to_players(message: Message, state: FSMContext) -> None:
    chat_name = message.chat.title
    word, theme = select_word_theme()
    data = (await state.get_data())["session_data"]
    players = data["players"]
    imposters = get_imposters(list(players.keys()))  # TODO: сделать рандомное количество
    order = get_random_order(list(players.keys()))
    data["imposters"] = imposters
    if imposters is None:
        data["imposters_num"] = 0
    else:
        data["imposters_num"] = len(imposters)
    data["order"] = order
    data["order"] = order
    data["word"] = word
    data["current_player"] = 0
    data["current_round"] = 1
    chat_id = data["chat_id"]
    for p_id in players:
        try:
            if imposters is not None and p_id in imposters:
                await message.bot.send_message(p_id, f"Вы предатель!!! Тема - {theme}, удачи:)")
            else:
                await message.bot.send_message(p_id, f"Вы получаете слово {word} (тема - {theme}) из чата {chat_name}!")
        except TelegramForbiddenError:
            await message.bot.send_message(message.chat.id, f"Игрок {players[p_id]} еблан.")

    await message.bot.send_message(
        chat_id,
        "Я отправил каждому игроку сообщение с его ролью и словом. Чтобы написать ассоциацию в свой ход введите /a 'ассоциация'. Если хотите начать голосование заранее, введите /vote",
    )
    await message.bot.send_message(chat_id, f"Раунд: 1/{NUM_ROUNDS}.")
    await message.bot.send_message(chat_id, f"Ассоциацию называет {players[order[0]]}.")

    await state.update_data(session_data=data)
    await state.set_state(States.WatchingAssoc)


@router.message(Command("a"))
async def association_round(message: Message, state: FSMContext, command: CommandObject) -> None:
    cur = await state.get_state()
    if cur != States.WatchingAssoc.state:
        return

    data = (await state.get_data())["session_data"]
    current_round = data["current_round"]
    current_player = data["current_player"]
    player_num = data["player_num"]
    order = data["order"]
    players = data["players"]
    if order[current_player] != message.from_user.id:
        await message.reply(f"Сейчас ход игрока: {players[order[current_player]]}")
        return

    if not command.args:
        await message.reply(f"Введите ассоциацию в формате '/a <ассоциация>'")
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
    players = data["players"]
    vote_button_arr = [InlineKeyboardButton(text=v, callback_data=f"vote{k}") for k, v in players.items()]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[vote_button_arr])
    await message.bot.send_message(message.chat.id, text="Проголосуйте за импостера", reply_markup=reply_markup)

    vote_str = "\n".join(f"{v}: 0" for v in players.values())
    msg = await message.bot.send_message(message.chat.id, f"Голоса:\n{vote_str}")
    data["msg_id"] = msg.message_id
    await state.update_data(session_data=data)


async def update_voting_message(message: Message, state: FSMContext) -> None:
    data = (await state.get_data())["session_data"]
    players = data["players"]
    votes = data["votes"]

    vote_str = "\n".join(f"{players[k]}: {votes[k]}" for k in players.keys())
    msg_id = data["msg_id"]
    await message.bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text=f"Голоса:\n{vote_str}")


@router.message(Command("vote"))
async def force_vote(message: Message, state: FSMContext) -> None:
    cur = await state.get_state()
    if cur != States.WatchingAssoc.state:
        return

    await state.set_state(States.Voting)
    await message.bot.send_message(message.chat.id, "Начинаем голосование заранее!")
    await send_voting_message(message, state)


@router.callback_query(F.data.startswith("vote"))
async def vote_for_imposter(callback: CallbackQuery, state: FSMContext) -> None:
    cur = await state.get_state()
    if cur != States.Voting.state:
        return

    data = (await state.get_data())["session_data"]
    voted = data["voted"]
    votes = data["votes"]
    players = data["players"]
    voter_id = callback.from_user.id
    voted_id = int(callback.data[4:])
    if voter_id in voted or voter_id == voted_id:
        return

    votes[voted_id] += 1
    voted.append(voter_id)
    data["votes"] = votes
    data["voted"] = voted

    await state.update_data(session_data=data)
    await update_voting_message(callback.message, state)

    if len(voted) == len(players):
        await state.set_state(States.GameFinish)
        await finish_game(callback.message, state)


async def finish_game(message: Message, state: FSMContext) -> None:
    data = (await state.get_data())["session_data"]
    imposters = data["imposters"]
    votes = data["votes"]
    players = data["players"]
    max_voted = max(votes.values())
    max_voted_ids = [i for i in votes.keys() if votes[i] == max_voted]
    if imposters is None:
        await message.bot.send_message(message.chat.id, "Импостеров не было, зачилльтесь!")
        await state.set_state(None)
        return
    if len(max_voted_ids) == 1:
        voted_id = max_voted_ids[0]
        await message.bot.send_message(
            message.chat.id, f"Голосованием выбран единственный импостер - {players[voted_id]}"
        )
        if voted_id in imposters:
            if len(imposters) == 1:
                await message.bot.send_message(
                    message.chat.id, f"Вы угадали единственного импостера - {players[voted_id]}! Победили силы света:)"
                )
            else:
                await message.bot.send_message(
                    message.chat.id,
                    f"Вы угадали одного из импостеров, импостерами были {', '.join(players[i] for i in imposters)}!",
                )
        else:
            if len(imposters) == 1:
                await message.bot.send_message(
                    message.chat.id, f"Неверный выбор! Победа за импостером - {players[imposters[0]]}!"
                )
            else:
                await message.bot.send_message(
                    message.chat.id,
                    f"Неверный выбор! Победа за импостерами - {', '.join(players[i] for i in imposters)}!",
                )
    else:
        if set(max_voted_ids).issubset(set(imposters)):
            await message.bot.send_message(
                message.chat.id,
                f"Все кого вы выбрали были импостерами, вот полный список: {', '.join(players[i] for i in imposters)}",
            )
        else:
            if len(imposters) == 1:
                await message.bot.send_message(
                    message.chat.id, f"Неверный выбор! Победа за импостером - {players[imposters[0]]}!"
                )
            else:
                await message.bot.send_message(
                    message.chat.id,
                    f"Неверный выбор! Победа за импостерами - {', '.join(players[i] for i in imposters)}!",
                )

    await state.set_state(None)


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    dp.include_router(router)
    init_db()
    load_data_from_file("example_words.txt")
    await set_bot_commands(bot)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
