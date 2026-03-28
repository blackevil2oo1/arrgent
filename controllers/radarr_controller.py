"""
radarr_controller.py – Steuert Radarr (Film-Downloader).

Verfügbare Funktionen:
- search_movie(title)                        → sucht einen Film, gibt Treffer zurück
- get_quality_profiles()                     → listet verfügbare Qualitätsprofile
- add_movie(tmdb_id, title, year,
            quality_profile_id)              → fügt einen Film zur Download-Warteschlange hinzu
- get_recent_movies(days)                    → gibt neu hinzugekommene Filme zurück
"""

import httpx
from .base import BaseController
import config


class RadarrController(BaseController):

    def __init__(self):
        super().__init__(config.RADARR_URL, config.RADARR_API_KEY)

    def search_movie(self, title: str) -> list[dict]:
        """
        Sucht nach einem Film in der Radarr-Datenbank.
        Gibt eine Liste von Treffern zurück mit Titel, Jahr und TMDB-ID.
        """
        response = httpx.get(
            f"{self.base_url}/api/v3/movie/lookup",
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
                "tmdb_id": item.get("tmdbId"),
                "overview": item.get("overview", "")[:200],
                "already_in_radarr": item.get("id", 0) != 0,
            })
        return results

    def get_quality_profiles(self) -> list[dict]:
        """
        Gibt alle verfügbaren Qualitätsprofile aus Radarr zurück.
        Wird aufgerufen bevor add_movie, damit der User wählen kann.
        """
        response = httpx.get(
            f"{self.base_url}/api/v3/qualityprofile",
            headers=self._headers(),
            timeout=15,
        )
        response.raise_for_status()
        return [{"profile_id": p["id"], "name": p["name"]} for p in response.json()]

    def add_movie(self, tmdb_id: int, title: str, year: int, quality_profile_id: int) -> dict:
        """
        Fügt einen Film zu Radarr hinzu und startet den Download.
        quality_profile_id muss vorher via get_quality_profiles ermittelt werden.
        """
        # Prüfen ob Film bereits in Radarr vorhanden ist
        check = httpx.get(
            f"{self.base_url}/api/v3/movie/lookup",
            params={"term": f"tmdb:{tmdb_id}"},
            headers=self._headers(),
            timeout=30,
        )
        check.raise_for_status()
        items = check.json()
        if items and items[0].get("id", 0) != 0:
            return {
                "success": True,
                "already_exists": True,
                "title": title,
                "message": f"'{title}' ist bereits in deiner Sammlung vorhanden.",
            }

        folders = httpx.get(
            f"{self.base_url}/api/v3/rootfolder",
            headers=self._headers(),
            timeout=15,
        )
        folders.raise_for_status()
        folder_list = folders.json()
        if not folder_list:
            return {"success": False, "error": "Keine Root-Folder in Radarr konfiguriert."}
        root_folder = folder_list[0]["path"]

        payload = {
            "title": title,
            "year": year,
            "tmdbId": tmdb_id,
            "qualityProfileId": quality_profile_id,
            "rootFolderPath": root_folder,
            "monitored": True,
            "addOptions": {"searchForMovie": True},
        }

        response = httpx.post(
            f"{self.base_url}/api/v3/movie",
            json=payload,
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
        return {"success": True, "title": title, "year": year}

    def get_recent_movies(self, limit: int = 10) -> list[dict]:
        """
        Gibt die zuletzt tatsächlich heruntergeladenen Filme zurück (via Radarr-History).
        """
        response = httpx.get(
            f"{self.base_url}/api/v3/history",
            params={"pageSize": 50, "sortKey": "date", "sortDirection": "descending"},
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()

        seen_ids: set = set()
        result = []
        for event in response.json().get("records", []):
            if event.get("eventType") != "downloadFolderImported":
                continue
            movie = event.get("movie", {})
            movie_id = event.get("movieId") or movie.get("id")
            if not movie_id or movie_id in seen_ids:
                continue
            seen_ids.add(movie_id)
            result.append({
                "title": movie.get("title") or event.get("sourceTitle", "").split(".")[0],
                "year": movie.get("year"),
            })
            if len(result) >= limit:
                break
        return result
