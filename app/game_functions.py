from random import choice, sample, shuffle

from db import Word


def get_random_order(players: list[int]) -> list[int]:
    order = players.copy()
    shuffle(order)
    return order


def get_imposters(players: list[int], impostor_num: int) -> list[int]:
    return sample(players, impostor_num)


def select_word_theme() -> tuple[str, str]:
    words: list[Word] = list(Word.select())
    w = choice(words)
    t = w.theme
    return w.name, t.name
