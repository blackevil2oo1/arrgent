"""
book_controller.py – Sucht Bücher/Hörbücher und startet den Download.

Ablauf:
1. search_books(title, book_type, chat_id)  → sucht auf SceneNZB, cacht NZB-URLs pro Chat
2. get_book_libraries(book_type)            → listet Bibliotheken
3. download_book(index, title, ..., chat_id)→ liest URL aus Chat-Cache per Index (1-8)

Die KI übergibt nur den Index (die Nummer die der User gewählt hat) – keine URLs, keine IDs.

SABnzbd-Kategorien:
- Ebooks:     eine Kategorie "ebooks" für alle User → Calibre Auto-Add-Ordner
- Hörbücher:  eine Kategorie pro User: "audiobook_tim", "audiobook_lina" usw.
              → jeweiliger Audiobookshelf-Bibliotheksordner
"""

import logging
import time
import httpx
import config

log = logging.getLogger("bot.book")

# Pro Chat werden die Suchergebnisse der letzten Suche gespeichert.
# Index 0 = Eintrag 1 in der Liste die dem User gezeigt wurde.
# Format: { chat_id: [ {"url": ..., "title": ..., "book_type": ...}, ... ] }
_search_cache: dict[int, list[dict]] = {}

# Zeitstempel wann der Cache zuletzt gesetzt wurde (für Timeout-Prüfung)
_search_cache_ts: dict[int, float] = {}


def _load_users() -> list[dict]:
    raw = config.BOOK_USERS
    names = [n.strip() for n in raw.split(",") if n.strip()]
    return [{"name": n, "id": _normalize(n)} for n in names]


def _normalize(name: str) -> str:
    return (
        name.lower()
        .replace(" ", "_")
        .replace("ü", "ue")
        .replace("ö", "oe")
        .replace("ä", "ae")
        .replace("ß", "ss")
    )


class BookController:

    # ── SceneNZB-Suche ─────────────────────────────────────────────────────────

    def search_books(self, title: str, book_type: str, chat_id: int = 0) -> list[dict]:
        """Sucht auf SceneNZB. book_type: 'ebook' oder 'audiobook'."""
        categories = "3130" if book_type == "audiobook" else "7100"

        response = httpx.get(
            f"{config.SCENENZB_URL}/api",
            params={
                "apikey": config.SCENENZB_API_KEY,
                "t": "search",
                "q": title,
                "cat": categories,
                "o": "json",
                "limit": 10,
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()

        items = data.get("channel", {}).get("item", [])
        if isinstance(items, dict):
            items = [items]

        nzb_urls = []
        results = []
        for i, item in enumerate(items[:8]):
            size_bytes = 0
            for attr in item.get("newznab:attr", []):
                a = attr.get("@attributes", {})
                if a.get("name") == "size":
                    size_bytes = int(a.get("value", 0))
            if not size_bytes:
                enc = item.get("enclosure", {}).get("@attributes", {})
                size_bytes = int(enc.get("length", 0))

            title = item.get("title", "")
            nzb_urls.append({"url": item.get("link", ""), "title": title, "book_type": book_type})
            results.append({
                "index": i + 1,
                "title": title,
                "size_mb": round(size_bytes / 1024 / 1024, 1) if size_bytes else None,
                "date": item.get("pubDate", "")[:22],
            })

        # Suchergebnisse für diesen Chat cachen (Index 0 = Listeneintrag 1)
        _search_cache[chat_id] = nzb_urls
        _search_cache_ts[chat_id] = time.time()
        log.info(f"[search_books] chat_id={chat_id} | {len(nzb_urls)} Ergebnisse gecacht")

        return results

    # ── Bibliotheken auflisten ─────────────────────────────────────────────────

    def get_audiobook_libraries(self) -> list[dict]:
        """Gibt alle Audiobookshelf-Bibliotheken zurück."""
        response = httpx.get(
            f"{config.AUDIOBOOKSHELF_URL}/api/libraries",
            headers={"Authorization": f"Bearer {config.AUDIOBOOKSHELF_TOKEN}"},
            timeout=10,
        )
        response.raise_for_status()
        return [
            {"id": lib["id"], "name": lib["name"]}
            for lib in response.json().get("libraries", [])
        ]

    def get_ebook_libraries(self) -> list[dict]:
        """
        Gibt die User-Liste zurück (aus BOOK_USERS).
        Alle Ebooks landen in einer SABnzbd-Kategorie 'ebooks'.
        Die Auswahl dient nur der Bestätigungsnachricht.
        """
        users = _load_users()
        if not users:
            return [{"id": "alle", "name": "Allgemein"}]
        return [{"id": u["id"], "name": u["name"]} for u in users]

    # ── Download starten ───────────────────────────────────────────────────────

    def download_book(
        self,
        index: int,
        title: str,
        library_id: str = "ebooks",
        book_type: str = "ebook",
        chat_id: int = 0,
    ) -> dict:
        """
        Fügt ein Buch oder Hörbuch zur SABnzbd-Warteschlange hinzu.

        index: Nummer aus der Ergebnisliste (1-8) die der User gewählt hat.
        Die NZB-URL wird aus dem Chat-Cache geladen – die KI übergibt keine URLs.
        """
        cached = _search_cache.get(chat_id, [])
        log.info(f"[download_book] chat_id={chat_id} index={index} | {len(cached)} Einträge im Cache")

        if not cached or index < 1 or index > len(cached):
            return {
                "success": False,
                "message": f"Kein Suchergebnis für Index {index}. Bitte erneut suchen.",
            }

        nzb_url = cached[index - 1]["url"]
        return self._download_nzb(nzb_url, title, library_id, book_type, chat_id)

    def download_book_by_url(
        self,
        nzb_url: str,
        title: str,
        library_id: str = "ebooks",
        book_type: str = "ebook",
        chat_id: int = 0,
    ) -> dict:
        """Direkter Download per URL – für den Hörbuch-Zwei-Schritt-Flow im Handler."""
        return self._download_nzb(nzb_url, title, library_id, book_type, chat_id)

    def _download_nzb(
        self,
        nzb_url: str,
        title: str,
        library_id: str,
        book_type: str,
        chat_id: int,
    ) -> dict:

        if book_type == "audiobook":
            lib_info = self._get_audiobook_library_info(library_id)
            sabnzbd_category = lib_info["category"]
            lib_name = lib_info["name"]
        else:
            sabnzbd_category = "ebooks"
            lib_name = "Calibre"

        # NZB-Inhalt herunterladen und direkt an SABnzbd übergeben
        try:
            nzb_response = httpx.get(nzb_url, timeout=30, follow_redirects=True)
            nzb_response.raise_for_status()
        except Exception as e:
            print(f"[download_book] NZB-Download fehlgeschlagen ({nzb_url[:80]}): {e}")
            raise

        try:
            response = httpx.post(
                f"{config.SABNZBD_URL}/api",
                data={
                    "apikey": config.SABNZBD_API_KEY,
                    "output": "json",
                    "mode": "addfile",
                    "nzbname": title,
                    "cat": sabnzbd_category,
                },
                files={"name": (f"{title}.nzb", nzb_response.content, "application/x-nzb")},
                timeout=15,
            )
        except Exception as e:
            print(f"[download_book] SABnzbd nicht erreichbar ({config.SABNZBD_URL}): {e}")
            raise
        response.raise_for_status()
        data = response.json()

        if data.get("status") is not True:
            return {"success": False, "message": f"SABnzbd-Fehler: {data}"}

        result = {
            "success": True,
            "message": f"'{title}' für {lib_name} wird heruntergeladen.",
            "sabnzbd_category": sabnzbd_category,
        }

        if book_type == "audiobook":
            scan = self._trigger_audiobookshelf_scan(library_id)
            result["scan_triggered"] = scan["success"]
            result["note"] = (
                "Audiobookshelf-Scan gestartet. Das Hörbuch erscheint "
                "sobald der Download abgeschlossen ist."
            )

        return result

    # ── Hilfsfunktionen ────────────────────────────────────────────────────────

    def _get_audiobook_library_info(self, library_id: str) -> dict:
        """SABnzbd-Kategorie = 'audiobook_{normalisierter_name}'."""
        try:
            response = httpx.get(
                f"{config.AUDIOBOOKSHELF_URL}/api/libraries/{library_id}",
                headers={"Authorization": f"Bearer {config.AUDIOBOOKSHELF_TOKEN}"},
                timeout=10,
            )
            response.raise_for_status()
            name = response.json().get("name", "default")
            return {"name": name, "category": f"audiobook_{_normalize(name)}"}
        except Exception:
            return {"name": "default", "category": "audiobook_default"}

    def _trigger_audiobookshelf_scan(self, library_id: str) -> dict:
        """Startet einen Bibliotheks-Scan in Audiobookshelf."""
        try:
            response = httpx.post(
                f"{config.AUDIOBOOKSHELF_URL}/api/libraries/{library_id}/scan",
                headers={"Authorization": f"Bearer {config.AUDIOBOOKSHELF_TOKEN}"},
                timeout=10,
            )
            response.raise_for_status()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
