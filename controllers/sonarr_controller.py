"""
sonarr_controller.py – Steuert Sonarr (Serien-Downloader).

Verfügbare Funktionen:
- search_series(title)        → sucht eine Serie, gibt Treffer zurück
- add_series(tvdb_id)         → fügt eine Serie zur Download-Warteschlange hinzu
- get_recent_series(days)     → gibt neu hinzugekommene Serien zurück
- get_series_updates(days)    → zeigt welche laufenden Serien neue Folgen bekommen haben
"""

import httpx
from .base import BaseController
import config


class SonarrController(BaseController):

    def __init__(self):
        super().__init__(config.SONARR_URL, config.SONARR_API_KEY)

    def search_series(self, title: str) -> list[dict]:
        """
        Sucht nach einer Serie in der Sonarr-Datenbank.
        Gibt eine Liste von Treffern zurück mit Titel, Jahr und TVDB-ID.
        """
        response = httpx.get(
            f"{self.base_url}/api/v3/series/lookup",
            params={"term": title},
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()

        results = []
        for item in response.json()[:5]:  # maximal 5 Treffer
            results.append({
                "title": item.get("title"),
                "year": item.get("year"),
                "tvdb_id": item.get("tvdbId"),
                "overview": item.get("overview", "")[:200],
                "already_in_sonarr": item.get("id", 0) != 0,
            })
        return results

    def get_quality_profiles(self) -> list[dict]:
        """Gibt alle verfügbaren Qualitätsprofile zurück."""
        response = httpx.get(
            f"{self.base_url}/api/v3/qualityprofile",
            headers=self._headers(),
            timeout=15,
        )
        response.raise_for_status()
        return [{"id": p["id"], "name": p["name"]} for p in response.json()]

    def add_series(self, tvdb_id: int, title: str, year: int, quality_profile_id: int) -> dict:
        """
        Fügt eine Serie zu Sonarr hinzu und startet den Download.
        """
        folders = httpx.get(
            f"{self.base_url}/api/v3/rootfolder",
            headers=self._headers(),
            timeout=15,
        )
        folders.raise_for_status()
        folder_list = folders.json()
        if not folder_list:
            return {"success": False, "error": "Keine Root-Folder in Sonarr konfiguriert."}
        root_folder = folder_list[0]["path"]

        # Erst Lookup machen um vollständige Daten zu bekommen
        lookup = httpx.get(
            f"{self.base_url}/api/v3/series/lookup",
            params={"term": f"tvdb:{tvdb_id}"},
            headers=self._headers(),
            timeout=30,
        )
        lookup.raise_for_status()
        lookup_results = lookup.json()
        if not lookup_results:
            return {"success": False, "error": f"Serie mit TVDB-ID {tvdb_id} nicht gefunden."}
        series_data = lookup_results[0]

        # Serie bereits in Sonarr → nicht nochmal hinzufügen
        if series_data.get("id", 0) != 0:
            return {"success": True, "already_exists": True, "title": title, "year": year,
                    "message": f"'{title}' ist bereits in Sonarr vorhanden."}

        series_data.update({
            "qualityProfileId": int(quality_profile_id),
            "rootFolderPath": root_folder,
            "monitored": True,
            "addOptions": {"searchForMissingEpisodes": True},
        })

        response = httpx.post(
            f"{self.base_url}/api/v3/series",
            json=series_data,
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
        return {"success": True, "title": title, "year": year}

    def get_series_updates(self, days: int = 7) -> list[dict]:
        """
        Zeigt welche überwachten Serien in den letzten X Tagen neue Folgen bekommen haben.
        Nutzt Sonarr-History (downloadFolderImported), gruppiert nach Serie.
        """
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        response = httpx.get(
            f"{self.base_url}/api/v3/history",
            params={
                "pageSize": 500,
                "sortKey": "date",
                "sortDirection": "descending",
                "includeSeries": "true",
                "includeEpisode": "true",
            },
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()

        # Gruppieren nach Serie: {series_id: {title, year, episodes: [...]}}
        series_map: dict = {}
        for event in response.json().get("records", []):
            if event.get("eventType") != "downloadFolderImported":
                continue
            date_str = event.get("date", "")
            if not date_str:
                continue
            event_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if event_date < cutoff:
                break  # History ist chronologisch, ältere Einträge ignorieren

            series = event.get("series", {})
            series_id = event.get("seriesId") or series.get("id")
            if not series_id:
                continue

            episode = event.get("episode", {})
            ep_info = f"S{episode.get('seasonNumber', 0):02d}E{episode.get('episodeNumber', 0):02d}"
            ep_title = episode.get("title", "")

            if series_id not in series_map:
                series_map[series_id] = {
                    "title": series.get("title", ""),
                    "year": series.get("year"),
                    "new_episodes": [],
                }
            series_map[series_id]["new_episodes"].append(
                ep_info + (f" – {ep_title}" if ep_title else "")
            )

        result = sorted(series_map.values(), key=lambda s: len(s["new_episodes"]), reverse=True)
        return result if result else [{"message": f"Keine neuen Folgen in den letzten {days} Tagen."}]

    def get_recent_series(self, limit: int = 10) -> list[dict]:
        """
        Gibt die zuletzt zu Sonarr hinzugefügten Serien zurück (nach 'added'-Datum).
        Nutzt die Series-API statt History, damit auch neu hinzugefügte Serien
        ohne bereits importierte Episoden erscheinen.
        """
        response = httpx.get(
            f"{self.base_url}/api/v3/series",
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()

        series_list = sorted(
            response.json(),
            key=lambda s: s.get("added", ""),
            reverse=True,
        )
        result = []
        for s in series_list[:limit]:
            result.append({
                "title": s.get("title", ""),
                "year": s.get("year"),
            })
        return result
