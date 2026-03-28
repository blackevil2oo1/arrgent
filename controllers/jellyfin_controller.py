"""
jellyfin_controller.py – Steuert Jellyfin (Medienserver).

Verfügbare Funktionen:
- trigger_library_scan()     → startet einen Bibliotheksscan
- get_recent_media(days)     → gibt neu hinzugekommene Medien zurück

Webhooks (werden von Jellyfin aktiv gesendet, kein Polling):
- Neuer Inhalt verfügbar     → postet in Telegram (Admin + User-Gruppe)
- Wiedergabefehler           → postet nur in Admin-Chat mit Fehlermeldung
"""

import httpx
from .base import BaseController
import config


class JellyfinController(BaseController):

    def __init__(self):
        super().__init__(config.JELLYFIN_URL, config.JELLYFIN_API_KEY)

    def _headers(self) -> dict:
        """Jellyfin verwendet einen anderen Header-Stil als Radarr/Sonarr."""
        return {
            "X-Emby-Token": self.api_key,
            "Content-Type": "application/json",
        }

    def trigger_library_scan(self) -> dict:
        """Startet einen vollständigen Bibliotheksscan in Jellyfin."""
        response = httpx.post(
            f"{self.base_url}/Library/Refresh",
            headers=self._headers(),
            timeout=15,
        )
        response.raise_for_status()
        return {"success": True, "message": "Bibliotheksscan wurde gestartet"}

    def get_recent_media(self, days: int = 7) -> list[dict]:
        """
        Gibt Filme und Serien zurück die in den letzten X Tagen
        zu Jellyfin hinzugekommen sind.
        """
        from datetime import datetime, timedelta

        params = {
            "SortBy": "DateCreated",
            "SortOrder": "Descending",
            "IncludeItemTypes": "Movie,Series",
            "Recursive": True,
            "Limit": 20,
            "Fields": "DateCreated,Overview",
        }

        response = httpx.get(
            f"{self.base_url}/Items",
            params=params,
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()

        from datetime import timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent = []

        for item in response.json().get("Items", []):
            created = item.get("DateCreated", "")
            if created:
                created_date = datetime.fromisoformat(created.replace("Z", "+00:00"))
                if created_date > cutoff:
                    recent.append({
                        "title": item.get("Name"),
                        "type": item.get("Type"),
                        "year": item.get("ProductionYear"),
                    })

        return recent
