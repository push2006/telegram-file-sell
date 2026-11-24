
import asyncio
from bot import Bot, web_app
from hydrogram import compose
from hydrogram.errors import InternalServerError
from config import *


async def main():
    while True:
        app = [
            Bot(
                SESSION,
                WORKERS,
                DB_CHANNEL,
                FSUBS,
                TOKEN,
                ADMINS,
                MESSAGES,
                AUTO_DEL,
                DB_URI,
                DB_NAME,
                API_ID,
                API_HASH,
                PROTECT,
                DISABLE_BTN
            )
        ]

        try:
            await compose(app)
            break

        except InternalServerError as e:
            print(f"Telegram server error: {e}", flush=True)

            for client in app:
                if client.is_connected:
                    await client.disconnect()

            print("Retrying after 60 seconds...", flush=True)
            await asyncio.sleep(60)


async def runner():
    await web_app()
    print("Web server started successfully", flush=True)
    await main()


if __name__ == "__main__":
    asyncio.run(runner())
