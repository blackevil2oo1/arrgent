"""
config.py – Lädt alle Einstellungen aus der .env Datei.

Alle anderen Dateien importieren ihre Einstellungen von hier.
Niemals direkt os.environ in anderen Dateien verwenden.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    """Gibt den Wert einer ENV-Variable zurück oder bricht ab wenn sie fehlt."""
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Fehlende ENV-Variable: {key} – bitte in .env eintragen")
    return value


# Telegram
TELEGRAM_BOT_TOKEN = _require("TELEGRAM_BOT_TOKEN")
TELEGRAM_ADMIN_CHAT_ID = int(_require("TELEGRAM_ADMIN_CHAT_ID"))
TELEGRAM_USER_GROUP_ID = int(_require("TELEGRAM_USER_GROUP_ID"))

# OpenAI
OPENAI_API_KEY = _require("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# TMDB
TMDB_API_KEY = _require("TMDB_API_KEY")

# App-Schalter (Standard: alle aktiv)
RADARR_ENABLED         = os.getenv("RADARR_ENABLED", "true").lower() == "true"
SONARR_ENABLED         = os.getenv("SONARR_ENABLED", "true").lower() == "true"
JELLYFIN_ENABLED       = os.getenv("JELLYFIN_ENABLED", "true").lower() == "true"
CALIBRE_ENABLED        = os.getenv("CALIBRE_ENABLED", "true").lower() == "true"
AUDIOBOOKSHELF_ENABLED = os.getenv("AUDIOBOOKSHELF_ENABLED", "true").lower() == "true"

# Radarr
RADARR_URL = os.getenv("RADARR_URL", "http://seedbox:7878")
RADARR_API_KEY = os.getenv("RADARR_API_KEY", "")

# Sonarr
SONARR_URL = os.getenv("SONARR_URL", "http://seedbox:8989")
SONARR_API_KEY = os.getenv("SONARR_API_KEY", "")

# Jellyfin
JELLYFIN_URL = os.getenv("JELLYFIN_URL", "http://seedbox:8096")
JELLYFIN_API_KEY = os.getenv("JELLYFIN_API_KEY", "")

# SABnzbd (immer benötigt solange Bücher/Hörbücher aktiv)
SABNZBD_URL = os.getenv("SABNZBD_URL", "http://seedbox:8080")
SABNZBD_API_KEY = os.getenv("SABNZBD_API_KEY", "")

# Webhook
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "9000"))

# SceneNZB
SCENENZB_URL = os.getenv("SCENENZB_URL", "https://scenenzbs.com")
SCENENZB_API_KEY = os.getenv("SCENENZB_API_KEY", "")

# User-Liste für Buch-/Hörbuch-Bibliotheken (kommagetrennt, z.B. "Tim,Lina,Anna")
BOOK_USERS = os.getenv("BOOK_USERS", "")

# Audiobookshelf (Hörbücher)
AUDIOBOOKSHELF_URL = os.getenv("AUDIOBOOKSHELF_URL", "http://seedbox:13378")
AUDIOBOOKSHELF_TOKEN = os.getenv("AUDIOBOOKSHELF_TOKEN", "")


def is_allowed_chat(chat_id: int) -> bool:
    """Prüft ob eine Nachricht aus einem erlaubten Chat kommt."""
    return chat_id in (TELEGRAM_ADMIN_CHAT_ID, TELEGRAM_USER_GROUP_ID)
