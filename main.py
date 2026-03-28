"""
main.py – Einstiegspunkt. Startet alles.

Startet:
1. Den Telegram Bot (empfängt Nachrichten)
2. Den Webhook-Server (empfängt Jellyfin-Ereignisse)
"""

import asyncio
import uvicorn
from telegram.ext import Application

import config
from logging_config import setup_logging
from messaging.telegram_handler import create_application
from messaging.webhook_server import app as webhook_app, init as init_webhook

log = setup_logging(debug=False)


async def main():
    log.info("Arrgent wird gestartet...")

    # Telegram Bot erstellen
    telegram_app: Application = create_application()
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling()

    bot = telegram_app.bot

    # Webhook-Server mit dem Bot initialisieren
    init_webhook(
        bot=bot,
        admin_chat_id=config.TELEGRAM_ADMIN_CHAT_ID,
        user_group_id=config.TELEGRAM_USER_GROUP_ID,
    )

    # Webhook-Server im Hintergrund starten
    webhook_config = uvicorn.Config(
        app=webhook_app,
        host="0.0.0.0",
        port=config.WEBHOOK_PORT,
        log_level="warning",
    )
    webhook_server = uvicorn.Server(webhook_config)

    log.info(f"Arrgent gestartet. Webhook-Server läuft auf Port {config.WEBHOOK_PORT}")

    await webhook_server.serve()


if __name__ == "__main__":
    asyncio.run(main())
