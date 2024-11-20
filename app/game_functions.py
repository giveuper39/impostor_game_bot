from random import choice, sample, shuffle, randint, choices

from db import Word


def get_random_order(players: list[int]) -> list[int]:
    order = players.copy()
    shuffle(order)
    return order


def choose_impostors(player_count: int) -> int:

    if player_count <= 0:
        return 0

    weights = [0] * (player_count + 1)  
    for i in range(player_count + 1):
        if i == 1:
            weights[i] = 200
        elif i == 0:
            weights[i] = 50
        else:
            weights[i] = max(1, 100 - i * 15)

    return choices(range(player_count + 1), weights=weights, k=1)[0]


def get_imposters(players: list[int]) -> list[int] | None:
    impostor_num = choose_impostors(len(players))
    if impostor_num == 0:
        return None
    return sample(players, impostor_num)


def select_word_theme() -> tuple[str, str]:
    words: list[Word] = list(Word.select())
    w = choice(words)
    t = w.theme
    return w.name, t.name
