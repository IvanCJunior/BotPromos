from telegram_bot.client import client
from config.settings import PHONE

async def main():
    await client.start(phone=PHONE)

    print("\nGRUPOS ENCONTRADOS:\n")

    async for dialog in client.iter_dialogs():
        print(f"{dialog.name}")
        print(f"ID: {dialog.id}")
        print("-" * 60)

with client:
    client.loop.run_until_complete(main())