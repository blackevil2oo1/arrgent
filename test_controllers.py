"""
test_controllers.py – Schnelltest aller Controller-Funktionen.
Ruft jeden Endpunkt direkt auf und zeigt Ergebnis oder Fehler.
Ausführen: python test_controllers.py
"""

import sys
import json

PASS = "✓"
FAIL = "✗"
results = []


def test(name: str, fn):
    try:
        result = fn()
        short = json.dumps(result, ensure_ascii=False)[:120]
        print(f"{PASS} {name}: {short}")
        results.append((name, True, None))
    except Exception as e:
        print(f"{FAIL} {name}: {e}")
        results.append((name, False, str(e)))


# ── Radarr ──────────────────────────────────────────────────────────────────
from controllers.radarr_controller import RadarrController
radarr = RadarrController()

test("radarr.search_movie",         lambda: radarr.search_movie("The Matrix"))
test("radarr.get_quality_profiles", lambda: radarr.get_quality_profiles())
test("radarr.get_recent_movies",    lambda: radarr.get_recent_movies(5))

# ── Sonarr ───────────────────────────────────────────────────────────────────
from controllers.sonarr_controller import SonarrController
sonarr = SonarrController()

test("sonarr.search_series",        lambda: sonarr.search_series("Severance"))
test("sonarr.get_quality_profiles", lambda: sonarr.get_quality_profiles())
test("sonarr.get_recent_series",    lambda: sonarr.get_recent_series(5))
test("sonarr.get_series_updates",   lambda: sonarr.get_series_updates(14))

# ── Jellyfin ─────────────────────────────────────────────────────────────────
from controllers.jellyfin_controller import JellyfinController
jellyfin = JellyfinController()

test("jellyfin.get_recent_media",   lambda: jellyfin.get_recent_media(7))

# ── SABnzbd ──────────────────────────────────────────────────────────────────
from controllers.sabnzbd_controller import SabnzbdController
sabnzbd = SabnzbdController()

test("sabnzbd.get_queue",           lambda: sabnzbd.get_queue())

# ── Bücher (SceneNZB) ─────────────────────────────────────────────────────────
from controllers.book_controller import BookController
books = BookController()

test("books.search_ebook",          lambda: books.search_books("Dune", "ebook", chat_id=0))
test("books.search_audiobook",      lambda: books.search_books("Dune", "audiobook", chat_id=0))
test("books.get_audiobook_libs",    lambda: books.get_audiobook_libraries())

# ── Intent Classifier ────────────────────────────────────────────────────────
from ai.intent_classifier import classify, Intent

intent_cases = [
    ("neue folgen",                   Intent.SERIES_UPDATES),
    ("welche serie hat neue episoden",Intent.SERIES_UPDATES),
    ("was gibt es neues",             Intent.LATEST_MEDIA),
    ("lade den film inception",       Intent.DOWNLOAD_MOVIE),
    ("lade die serie breaking bad",   Intent.DOWNLOAD_SERIES),
    ("suche das buch harry potter",   Intent.SEARCH_BOOK),
    ("hörbuch herunterladen",         Intent.DOWNLOAD_BOOK),
]
print("\n── Intent Classifier ──")
for text, expected in intent_cases:
    got = classify(text)
    ok = got == expected
    mark = PASS if ok else FAIL
    print(f"{mark} '{text}' → {got}{'' if ok else ' (erwartet: ' + expected + ')'}")
    results.append((f"intent:{text}", ok, None if ok else f"got {got}, expected {expected}"))

# ── Zusammenfassung ───────────────────────────────────────────────────────────
print("\n" + "="*60)
passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
print(f"Ergebnis: {passed} bestanden, {failed} fehlgeschlagen")
if failed:
    print("\nFehler:")
    for name, ok, err in results:
        if not ok:
            print(f"  {FAIL} {name}: {err}")
