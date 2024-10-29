import peewee

db = peewee.SqliteDatabase("database.db")


class BaseModel(peewee.Model):
    class Meta:
        database = db


class Theme(BaseModel):
    name = peewee.CharField(unique=True)

class Word(BaseModel):
    name = peewee.CharField(unique=True)
    theme = peewee.ManyToManyField(Theme)


WordThemeMiddle = Word.theme.get_through_model()

