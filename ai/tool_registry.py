"""
tool_registry.py – Verbindet ChatGPT mit den Controllern.

Hier passiert die Magie:
1. Wir beschreiben ChatGPT welche Funktionen es aufrufen kann (TOOLS Liste)
2. Wenn ChatGPT entscheidet eine Funktion aufzurufen, führt dispatch() sie aus

Neuen Controller hinzufügen:
1. Controller unten importieren
2. Funktion in TOOLS beschreiben
3. Funktion in dispatch() eintragen
"""

import logging
import config

log = logging.getLogger("bot.registry")

from controllers.radarr_controller import RadarrController
from controllers.sonarr_controller import SonarrController
from controllers.jellyfin_controller import JellyfinController
from controllers.sabnzbd_controller import SabnzbdController
from controllers.book_controller import BookController

# Controller-Instanzen (einmalig erstellt, werden wiederverwendet)
radarr = RadarrController()
sonarr = SonarrController()
jellyfin = JellyfinController()
sabnzbd = SabnzbdController()
books = BookController()


# ─── Tool-Definitionen ──────────────────────────────────────────────────────

_RADARR_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_movie",
            "description": "Sucht nach einem Film. Aufrufen wenn der User einen Film sucht, hinzufügen oder herunterladen möchte.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Titel des Films"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_radarr_quality_profiles",
            "description": (
                "Gibt die verfügbaren Qualitätsprofile aus Radarr zurück – jedes mit 'profile_id' und 'name'. "
                "Vor add_movie aufrufen. Die Profile dem User mit Namen auflisten (z.B. '1. HD-1080p  2. 4K'). "
                "Wenn der User ein Profil wählt, den 'profile_id'-Wert aus dem Ergebnis für quality_profile_id verwenden – "
                "NIEMALS die Positionsnummer in der Liste (1, 2, 3…) als ID benutzen."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_movie",
            "description": (
                "Fügt einen Film zu Radarr hinzu und startet den Download. "
                "Ablauf: 1) get_radarr_quality_profiles aufrufen, 2) Profile dem User zeigen, "
                "3) User wählt Profil, 4) den 'profile_id'-Wert des gewählten Profils als quality_profile_id übergeben, "
                "5) add_movie aufrufen. WICHTIG: quality_profile_id ist der 'profile_id'-Wert aus dem API-Ergebnis, "
                "nicht die Nummer in der angezeigten Liste."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tmdb_id": {"type": "integer", "description": "TMDB ID des Films"},
                    "title": {"type": "string", "description": "Titel des Films"},
                    "year": {"type": "integer", "description": "Erscheinungsjahr"},
                    "quality_profile_id": {"type": "integer", "description": "Der 'profile_id'-Wert aus dem get_radarr_quality_profiles Ergebnis – nicht die Listennummer"},
                },
                "required": ["tmdb_id", "title", "year", "quality_profile_id"],
            },
        },
    },
]

_SONARR_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_series",
            "description": "Sucht nach einer Serie. Aufrufen wenn der User eine Serie sucht, hinzufügen oder herunterladen möchte.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Titel der Serie"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sonarr_quality_profiles",
            "description": (
                "Gibt die verfügbaren Qualitätsprofile aus Sonarr zurück – jedes mit 'profile_id' und 'name'. "
                "Vor add_series aufrufen. Die Profile dem User mit Namen auflisten (z.B. '1. HD-1080p  2. 4K'). "
                "Wenn der User ein Profil wählt, den 'profile_id'-Wert aus dem Ergebnis für quality_profile_id verwenden – "
                "NIEMALS die Positionsnummer in der Liste (1, 2, 3…) als ID benutzen."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_series",
            "description": (
                "Fügt eine Serie zu Sonarr hinzu und startet den Download aller Episoden. "
                "Ablauf: 1) search_series aufrufen, 2) get_sonarr_quality_profiles aufrufen, "
                "3) Profile dem User zeigen, 4) User wählt Profil, "
                "5) den 'profile_id'-Wert des gewählten Profils als quality_profile_id übergeben, 6) add_series aufrufen. "
                "WICHTIG: quality_profile_id ist der 'profile_id'-Wert aus dem API-Ergebnis, "
                "nicht die Nummer in der angezeigten Liste."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tvdb_id": {"type": "integer", "description": "TVDB ID der Serie"},
                    "title": {"type": "string", "description": "Titel der Serie"},
                    "year": {"type": "integer", "description": "Erscheinungsjahr"},
                    "quality_profile_id": {"type": "integer", "description": "Der 'profile_id'-Wert aus dem get_sonarr_quality_profiles Ergebnis – nicht die Listennummer"},
                },
                "required": ["tvdb_id", "title", "year", "quality_profile_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_series_updates",
            "description": (
                "Zeigt welche laufenden Serien in den letzten Tagen neue Folgen bekommen haben. "
                "Aufrufen wenn der User fragt welche Serien neue Episoden haben, was es Neues bei "
                "Serien gibt, oder 'welche Serie hat neue Folgen'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Zeitraum in Tagen (Standard: 7)"},
                },
                "required": [],
            },
        },
    },
]

_BOOK_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_book",
            "description": (
                "Sucht auf SceneNZB nach einem Buch (Ebook) oder Hörbuch. "
                "Aufrufen wenn der User ein Buch oder Hörbuch suchen oder herunterladen möchte. "
                "book_type: 'ebook' für Bücher/Ebooks, 'audiobook' für Hörbücher."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Titel des Buchs oder Hörbuchs"},
                    "book_type": {
                        "type": "string",
                        "enum": ["ebook", "audiobook"],
                        "description": "Art des Inhalts: 'ebook' für Bücher, 'audiobook' für Hörbücher",
                    },
                },
                "required": ["title", "book_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_book_libraries",
            "description": (
                "Listet die verfügbaren Audiobookshelf-Bibliotheken auf. "
                "NUR für Hörbücher aufrufen – nicht für Ebooks. "
                "Ebooks landen immer automatisch in Calibre, keine Bibliotheksauswahl nötig."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "book_type": {
                        "type": "string",
                        "enum": ["audiobook"],
                        "description": "Immer 'audiobook' – für Ebooks nicht aufrufen",
                    },
                },
                "required": ["book_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "download_book",
            "description": (
                "Startet den Download eines Buchs oder Hörbuchs über SABnzbd. "
                "Für Ebooks: 1) search_book aufrufen, 2) Ergebnisse nummeriert anzeigen, 3) auf User-Auswahl warten, 4) download_book mit dem index der gewählten Nummer aufrufen. "
                "Für Hörbücher: 1) search_book, 2) Ergebnisse anzeigen, 3) User wählt Nummer, 4) get_book_libraries aufrufen, 5) User wählt Bibliothek, 6) download_book aufrufen. "
                "Niemals erneut search_book aufrufen wenn der User eine Nummer aus der bestehenden Liste wählt. "
                "library_id nur für Hörbücher aus get_book_libraries-Ergebnis nehmen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "Die Nummer (1-8) die der User aus der Ergebnisliste gewählt hat"},
                    "title": {"type": "string", "description": "Titel des Buchs/Hörbuchs"},
                    "library_id": {
                        "type": "string",
                        "description": "Nur für Hörbücher: Audiobookshelf-Bibliotheks-ID aus get_book_libraries. Für Ebooks weglassen.",
                    },
                    "book_type": {
                        "type": "string",
                        "enum": ["ebook", "audiobook"],
                        "description": "Art des Inhalts",
                    },
                },
                "required": ["index", "title", "book_type"],
            },
        },
    },
]

_RECENT_MEDIA_TOOL = {
    "type": "function",
    "function": {
        "name": "get_recent_media",
        "description": (
            "Zeigt die letzten 10 heruntergeladenen Filme und Serien. "
            "Aufrufen wenn der User fragt was es Neues gibt, die letzten Downloads sehen möchte, "
            "oder nach 'neueste Filme', 'letzte Serien', 'was wurde geladen' fragt."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def get_tools() -> list:
    """Gibt die Tool-Liste basierend auf aktivierten Apps zurück."""
    tools = []

    if config.RADARR_ENABLED:
        tools.extend(_RADARR_TOOLS)
    if config.SONARR_ENABLED:
        tools.extend(_SONARR_TOOLS)
    if config.RADARR_ENABLED or config.SONARR_ENABLED:
        tools.append(_RECENT_MEDIA_TOOL)
    if config.CALIBRE_ENABLED or config.AUDIOBOOKSHELF_ENABLED:
        tools.extend(_BOOK_TOOLS)

    return tools


def dispatch(function_name: str, arguments: dict, chat_id: int = 0) -> str:
    """
    Führt die von ChatGPT gewählte Funktion aus.
    Gibt immer einen JSON-String zurück – auch bei Fehlern.

    Fehler werden strukturiert zurückgegeben damit die KI sie
    verständlich an den User weitergeben kann.
    """
    import json
    import httpx

    try:
        result = _call(function_name, arguments, chat_id)
        return json.dumps(result, ensure_ascii=False)

    except httpx.ConnectError:
        msg = f"[{function_name}] Dienst nicht erreichbar"
        log.error(msg)
        return json.dumps({"success": False, "error_type": "connection_error", "message": msg})

    except httpx.TimeoutException:
        msg = f"[{function_name}] Timeout – Dienst antwortet zu langsam"
        log.warning(msg)
        return json.dumps({"success": False, "error_type": "timeout", "message": msg})

    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text[:300]
        msg = f"[{function_name}] HTTP {e.response.status_code}: {detail}"
        log.error(msg)
        return json.dumps({
            "success": False,
            "error_type": "http_error",
            "status_code": e.response.status_code,
            "detail": detail,
            "message": f"API-Fehler {e.response.status_code} beim Aufruf von '{function_name}'.",
        })

    except KeyError as e:
        msg = f"[{function_name}] Pflichtparameter fehlt: {e}"
        log.error(msg)
        return json.dumps({"success": False, "error_type": "missing_argument", "message": msg})

    except Exception as e:
        msg = f"[{function_name}] Unerwarteter Fehler: {e}"
        log.error(msg, exc_info=True)
        return json.dumps({"success": False, "error_type": "unexpected_error", "message": msg})


def _call(name: str, args: dict, chat_id: int = 0):
    """Interner Router – mappt Funktionsname auf Controller-Aufruf."""
    match name:
        case "search_movie":
            return radarr.search_movie(args["title"])
        case "get_radarr_quality_profiles":
            return radarr.get_quality_profiles()
        case "add_movie":
            return radarr.add_movie(
                args["tmdb_id"], args["title"], args["year"], args["quality_profile_id"]
            )
        case "search_series":
            return sonarr.search_series(args["title"])
        case "get_sonarr_quality_profiles":
            return sonarr.get_quality_profiles()
        case "add_series":
            return sonarr.add_series(args["tvdb_id"], args["title"], args["year"], args["quality_profile_id"])
        case "get_series_updates":
            return sonarr.get_series_updates(args.get("days", 7))
        case "get_recent_media":
            movies, series = [], []
            try:
                movies = radarr.get_recent_movies(10)
            except Exception:
                pass
            try:
                series = sonarr.get_recent_series(10)
            except Exception:
                pass
            return {"movies": movies, "series": series}
        case "search_book":
            return books.search_books(args["title"], args["book_type"], chat_id=chat_id)
        case "get_book_libraries":
            if args["book_type"] == "audiobook":
                return books.get_audiobook_libraries()
            return books.get_ebook_libraries()
        case "download_book":
            book_type = args["book_type"]
            library_id = args.get("library_id")
            if book_type == "audiobook" and not library_id:
                return {
                    "success": False,
                    "error_type": "missing_argument",
                    "message": "Für Hörbücher muss zuerst get_book_libraries aufgerufen werden, damit der User eine Bibliothek wählen kann. library_id fehlt.",
                }
            return books.download_book(
                args["index"], args["title"], library_id or "ebooks", book_type,
                chat_id=chat_id,
            )
        case _:
            return {"error": f"Unbekannte Funktion: {name}"}
