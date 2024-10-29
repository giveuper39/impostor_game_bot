run:
	poetry run python app/bot.py

lint:
	poetry run ruff check . --fix
