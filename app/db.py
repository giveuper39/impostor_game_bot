import peewee

db = peewee.SqliteDatabase("main.db")


class BaseModel(peewee.Model):
    class Meta:
        database = db


class Theme(BaseModel):
    name = peewee.CharField(unique=True)


class Word(BaseModel):
    name = peewee.CharField(unique=True)
    theme = peewee.ForeignKeyField(Theme, backref="themes")


def init_db():
    if db.is_closed():
        db.connect()
    db.create_tables([Word, Theme], safe=True)
    db.close()


def load_data_from_file(file_path):
    if Word.select().count() != 0:
        return
    with open(file_path, encoding="utf-8") as file:
        data = file.read()

    # Разбиваем строки по ";"
    pairs = data.split(";")
    for pair in pairs:
        if ":" in pair:
            word_name, theme_name = pair.split(":")
            word_name, theme_name = word_name.strip(), theme_name.strip()
            print(word_name, theme_name)

            # Находим или создаём тему
            theme, created = Theme.get_or_create(name=theme_name)

            # Создаём слово, привязанное к теме
            Word.create(name=word_name, theme=theme)
