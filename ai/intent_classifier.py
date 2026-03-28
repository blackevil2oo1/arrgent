"""
intent_classifier.py – Erkennt die Absicht des Users bevor GPT aufgerufen wird.

Warum das wichtig ist:
- GPT bekommt nur die Tools die für die Absicht relevant sind
- Spart Token-Kosten (weniger Tool-Definitionen im Prompt)
- Macht den Bot schneller (kürzere Prompts = schnellere Antworten)

Ablauf:
1. Text wird gegen Keyword-Patterns geprüft (kostenlos, sofort)
2. Passendes Intent gefunden → nur relevante Tools werden an GPT übergeben
3. Kein Pattern passt (UNKNOWN) → GPT bekommt alle Tools (Fallback)

Wenn neue Tools hinzugefügt werden:
- Neues Intent in der Intent-Enum ergänzen
- Keywords in _PATTERNS eintragen
- Tool-Namen in INTENT_TOOLS eintragen
"""

from enum import Enum


class Intent(str, Enum):
    DOWNLOAD_MOVIE    = "download_movie"
    SEARCH_MOVIE      = "search_movie"
    DOWNLOAD_SERIES   = "download_series"
    SEARCH_SERIES     = "search_series"
    LATEST_MEDIA      = "latest_media"
    SEARCH_BOOK       = "search_book"
    DOWNLOAD_BOOK     = "download_book"
    SERIES_UPDATES    = "series_updates"
    UNKNOWN           = "unknown"


# Welche Tools gehören zu welchem Intent.
# None = alle Tools (bei UNKNOWN)
INTENT_TOOLS: dict[Intent, set[str] | None] = {
    Intent.DOWNLOAD_MOVIE:   {"search_movie", "get_radarr_quality_profiles", "add_movie"},
    Intent.SEARCH_MOVIE:     {"search_movie"},
    Intent.DOWNLOAD_SERIES:  {"search_series", "get_sonarr_quality_profiles", "add_series"},
    Intent.SEARCH_SERIES:    {"search_series"},
    Intent.LATEST_MEDIA:     {"get_recent_media"},
    Intent.SEARCH_BOOK:      {"search_book", "get_book_libraries", "download_book"},
    Intent.DOWNLOAD_BOOK:    {"search_book", "get_book_libraries", "download_book"},
    Intent.SERIES_UPDATES:   {"get_series_updates"},
    Intent.UNKNOWN:          None,
}

# Keyword-Listen pro Intent (alle Einträge lowercase).
# Reihenfolge ist wichtig: spezifischere Patterns vor allgemeineren.
_PATTERNS: list[tuple[Intent, list[str]]] = [
    (Intent.SERIES_UPDATES, [
        "neue folgen", "neue episoden", "neue staffel", "neue staffeln",
        "welche serie hat neue", "was gibt es neues bei serien",
        "serien update", "serien updates", "folgen neu", "episoden neu",
        "was ist neu bei serien", "neue folge", "neue episode",
    ]),
    (Intent.LATEST_MEDIA, [
        "was gibt es neues", "was ist neu", "neueste filme", "neueste serien",
        "zuletzt hinzugefügt", "neu hinzugekommen", "was kam neu", "was kam zuletzt",
        "neues auf dem server", "letzte downloads", "was wurde geladen",
        "was wurde heruntergeladen", "letzte filme", "letzte serien",
        "was ist zuletzt", "zuletzt geladen", "zuletzt heruntergeladen",
    ]),
    # Buch- und Hörbuch-Patterns (vor Serien/Film, da "buch" eindeutig)
    (Intent.DOWNLOAD_BOOK, [
        "buch herunterladen", "buch downloaden", "buch hinzufügen",
        "hörbuch herunterladen", "hörbuch downloaden", "hörbuch hinzufügen",
        "ebook herunterladen", "ebook downloaden", "ebook hinzufügen",
        "lade das buch", "lade das hörbuch", "füge das buch", "füge das hörbuch",
    ]),
    (Intent.SEARCH_BOOK, [
        "buch suchen", "suche buch", "suche das buch", "gibt es das buch", "finde das buch",
        "hörbuch suchen", "suche hörbuch", "suche das hörbuch", "gibt es das hörbuch",
        "ebook suchen", "suche ebook", "suche das ebook", "gibt es das ebook",
        "such das buch", "such das hörbuch", "such das ebook",
    ]),
    # Serien-Patterns vor Film-Patterns (da Überschneidungen möglich)
    (Intent.DOWNLOAD_SERIES, [
        "serie hinzufügen", "serie downloaden", "serie herunterladen",
        "lade die serie", "füge die serie", "serie zum download",
    ]),
    (Intent.SEARCH_SERIES, [
        "serie suchen", "suche serie", "gibt es die serie", "finde serie",
        "such die serie", "hast du die serie",
    ]),
    (Intent.DOWNLOAD_MOVIE, [
        "film hinzufügen", "film downloaden", "film herunterladen",
        "lade den film", "füge den film", "film zum download",
    ]),
    (Intent.SEARCH_MOVIE, [
        "film suchen", "suche film", "gibt es den film", "finde film",
        "such den film", "hast du den film",
    ]),
]


def classify(text: str) -> Intent:
    """
    Klassifiziert den Intent einer Nachricht anhand von Keywords.
    Gibt Intent.UNKNOWN zurück wenn kein Pattern passt.
    """
    normalized = text.lower().strip()
    for intent, keywords in _PATTERNS:
        if any(kw in normalized for kw in keywords):
            return intent
    return Intent.UNKNOWN


def filter_tools(intent: Intent, all_tools: list) -> list:
    """
    Gibt die für den Intent relevanten Tools zurück.
    Bei Intent.UNKNOWN werden alle Tools zurückgegeben.
    """
    relevant = INTENT_TOOLS.get(intent)
    if relevant is None:
        return all_tools
    return [t for t in all_tools if t["function"]["name"] in relevant]
