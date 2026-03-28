"""
webhook_server.py – Empfängt Webhooks von Jellyfin.

Jellyfin kann bei bestimmten Ereignissen automatisch eine HTTP-Anfrage senden:
- Wenn ein neuer Film/Serie verfügbar ist
- Wenn ein Wiedergabefehler auftritt

Dieser Server empfängt diese Anfragen und leitet sie als
Telegram-Nachricht weiter.

Jellyfin Webhook einrichten:
  Dashboard → Plugins → Webhook → Add
  URL: http://seedbox:9000/webhook/jellyfin
  Ereignisse: ItemAdded, PlaybackError (o.ä.)
"""

import logging
from fastapi import FastAPI, Request
import config

log = logging.getLogger("bot.webhook")

app = FastAPI()

# Wird beim Start von main.py gesetzt
_bot = None
_user_group_id = None
_admin_chat_id = None


def init(bot, admin_chat_id: int, user_group_id: int):
    """Initialisiert den Webhook-Server mit dem Telegram Bot."""
    global _bot, _admin_chat_id, _user_group_id
    _bot = bot
    _admin_chat_id = admin_chat_id
    _user_group_id = user_group_id


@app.post("/webhook/jellyfin")
async def jellyfin_webhook(request: Request):
    """Empfängt Webhooks von Jellyfin."""
    try:
        data = await request.json()
    except Exception:
        return {"status": "error", "detail": "invalid json"}
    event = data.get("NotificationType") or data.get("Event", "")

    log.info(f"Webhook empfangen: Event='{event}'")

    if "ItemAdded" in event:
        await _handle_new_item(data)
    elif "PlaybackError" in event or "Error" in event:
        await _handle_playback_error(data)

    return {"status": "ok"}


async def _handle_new_item(data: dict):
    """Neuer Inhalt wurde zu Jellyfin hinzugefügt."""
    if not _bot:
        return

    name = data.get("Name") or data.get("ItemName", "Unbekannt")
    item_type = data.get("ItemType", "")
    year = data.get("Year", "")

    type_label = "Film" if item_type == "Movie" else "Serie" if item_type == "Series" else item_type
    message = f"Neu verfügbar: {name} ({year}) [{type_label}]"
    log.info(f"Neuer Inhalt: {name} ({year}) [{type_label}]")

    # An beide Chats senden
    await _bot.send_message(chat_id=_admin_chat_id, text=message)
    await _bot.send_message(chat_id=_user_group_id, text=message)


async def _handle_playback_error(data: dict):
    """Wiedergabefehler – nur an Admin."""
    if not _bot:
        return

    user = data.get("NotificationUsername") or data.get("User", "Unbekannt")
    item = data.get("Name") or data.get("ItemName", "Unbekannt")
    error = data.get("Error") or data.get("Message", "Keine Details")

    message = (
        f"Wiedergabefehler\n"
        f"User: {user}\n"
        f"Inhalt: {item}\n"
        f"Fehler: {error}"
    )
    log.warning(f"Wiedergabefehler: User={user}, Inhalt={item}, Fehler={error}")

    await _bot.send_message(chat_id=_admin_chat_id, text=message)
