"""
sabnzbd_controller.py – Steuert SABnzbd (Download-Client).

Verfügbare Funktionen:
- get_queue()       → zeigt aktuelle Downloads und Warteschlange
- pause_queue()     → pausiert alle Downloads
- resume_queue()    → setzt Downloads fort
- get_history()     → zeigt abgeschlossene und fehlgeschlagene Downloads
"""

import httpx
from .base import BaseController
import config


class SabnzbdController(BaseController):

    def __init__(self):
        # SABnzbd hat keine separate base_url/api_key Trennung wie Radarr
        super().__init__(config.SABNZBD_URL, config.SABNZBD_API_KEY)

    def _api(self, mode: str, extra_params: dict = None) -> dict:
        """Interne Hilfsmethode – alle SABnzbd API Calls laufen über /api."""
        params = {
            "apikey": self.api_key,
            "output": "json",
            "mode": mode,
        }
        if extra_params:
            params.update(extra_params)

        response = httpx.get(f"{self.base_url}/api", params=params, timeout=15)
        response.raise_for_status()
        return response.json()

    def get_queue(self) -> dict:
        """
        Gibt die aktuelle Download-Warteschlange zurück.
        Enthält: aktive Downloads, Fortschritt, geschätzte Restzeit.
        """
        data = self._api("queue")
        queue = data.get("queue", {})

        return {
            "status": queue.get("status"),
            "speed": queue.get("speed"),
            "size_left": queue.get("sizeleft"),
            "time_left": queue.get("timeleft"),
            "items": [
                {
                    "name": item.get("filename"),
                    "status": item.get("status"),
                    "progress": item.get("percentage"),
                    "size": item.get("size"),
                }
                for item in queue.get("slots", [])[:10]
            ],
        }

    def pause_queue(self) -> dict:
        """Pausiert alle laufenden Downloads."""
        data = self._api("pause")
        if data.get("status") is not True:
            return {"success": False, "message": f"SABnzbd-Fehler beim Pausieren: {data}"}
        return {"success": True, "message": "Downloads pausiert"}

    def resume_queue(self) -> dict:
        """Setzt pausierte Downloads fort."""
        data = self._api("resume")
        if data.get("status") is not True:
            return {"success": False, "message": f"SABnzbd-Fehler beim Fortsetzen: {data}"}
        return {"success": True, "message": "Downloads fortgesetzt"}

    def get_history(self, limit: int = 10) -> list[dict]:
        """
        Gibt abgeschlossene und fehlgeschlagene Downloads zurück.
        Nützlich um zu sehen ob etwas schiefgelaufen ist.
        """
        data = self._api("history", {"limit": limit})
        items = data.get("history", {}).get("slots", [])

        return [
            {
                "name": item.get("name"),
                "status": item.get("status"),
                "size": item.get("size"),
                "failed_message": item.get("fail_message", ""),
            }
            for item in items
        ]
