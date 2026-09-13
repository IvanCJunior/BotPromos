from telethon import TelegramClient

from config.settings import (
    API_ID,
    API_HASH
)

client = TelegramClient(
    "bot_promos",
    API_ID,
    API_HASH
)