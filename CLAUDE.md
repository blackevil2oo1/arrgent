# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Modular Python Telegram bot that controls a seedbox/media server on Unraid.
User communicates via Telegram → OpenAI GPT-4o interprets → Controllers execute.

## Running the project

```bash
# Dependencies installieren
pip install -r requirements.txt

# Starten (lokal)
python main.py

# Als Docker Container
docker compose up --build
```

## Environment

Alle Konfiguration läuft über `.env`. Vorlage: `.env.example`.
Niemals `os.environ` direkt verwenden – immer über `config.py`.

## Architecture Rules

1. **Nur `ai/agent.py` darf OpenAI aufrufen.**
   Kein Controller, kein anderes Modul darf ein LLM verwenden oder importieren.

2. **Die KI erzeugt niemals Shell-Befehle oder Systembefehle.**
   Sie darf ausschließlich Tools aus `tool_registry.py` aufrufen.
   Dieses Verbot ist auch im `SYSTEM_PROMPT` in `agent.py` verankert.

3. **Konversationshistorie ist auf `MAX_HISTORY = 10` Nachrichten begrenzt** (pro Chat, in `telegram_handler.py`).
   Zweck: Tokenkosten begrenzen. Wert nicht ohne Grund erhöhen.

4. **OpenAI-Aufrufe haben immer einen Timeout** (`OPENAI_TIMEOUT = 20s` in `agent.py`).
   Verhindert dass der Bot bei langsamer API-Antwort dauerhaft blockiert.

5. **Controller dürfen niemals unkontrolliert Exceptions werfen.**
   `dispatch()` in `tool_registry.py` fängt alle Exceptions ab und gibt strukturierte
   Fehler-JSON zurück (`error_type`, `message`), damit die KI den Fehler verständlich
   an den User weitergeben kann.

6. **Intent-Klassifizierung vor jedem GPT-Call** (`ai/intent_classifier.py`).
   Keyword-Matching reduziert die Tool-Liste bevor GPT aufgerufen wird.
   Spart Token-Kosten und macht Antworten schneller.
   Bei neuen Tools: `Intent`, `INTENT_TOOLS` und `_PATTERNS` in `intent_classifier.py` ergänzen.

## Architecture

```
main.py                     # Startet Bot + Webhook-Server + Monitoring parallel
config.py                   # Zentrales ENV-Loading, is_admin_chat(), is_user_group()
messaging/
  telegram_handler.py       # Nachrichten empfangen, Konversationshistorie pro Chat
  webhook_server.py         # FastAPI auf Port 9000, empfängt Jellyfin-Webhooks
  monitor.py                # Asyncio-Loop, prüft Docker alle 60s
ai/
  agent.py                  # ChatGPT Multi-Round Tool-Loop (einziger OpenAI-Aufruf, max 5 Runden)
  tool_registry.py          # TOOLS-Liste für ChatGPT + dispatch() → Controller
  tmdb.py                   # TMDB API für Empfehlungen
controllers/
  base.py                   # BaseController mit _headers()
  radarr_controller.py      # Filme suchen/hinzufügen/neue abfragen
  sonarr_controller.py      # Serien suchen/hinzufügen/neue abfragen
  jellyfin_controller.py    # Bibliotheksscan, neue Medien abfragen
  sabnzbd_controller.py     # Queue, Pause/Resume, History
  docker_controller.py      # Container-Status, Neustart, abgestürzte erkennen
  system_controller.py      # Unraid API: CPU/RAM, Festplatten
  genre_sort_controller.py  # KI-gesteuerter Genre-Sortierer für Radarr-Filme
```

## Two-Chat Authorization

- **Admin-Chat** (`TELEGRAM_ADMIN_CHAT_ID`): alle Funktionen
- **User-Gruppe** (`TELEGRAM_USER_GROUP_ID`): nur `USER_ALLOWED_TOOLS` in `tool_registry.py`
- Unterscheidung per `chat_id`, nicht per `user_id`

## Proactive Notifications

- Jellyfin Webhook → neuer Inhalt → beide Chats; Wiedergabefehler → nur Admin
- `monitor.py` polling → Docker-Absturz → nur Admin
- `send_notification()` in `telegram_handler.py` für alle proaktiven Nachrichten

## Adding a new controller

1. `controllers/xxx_controller.py` erstellen, von `BaseController` erben
2. Tool-Definition zur `TOOLS`-Liste in `tool_registry.py` hinzufügen
3. `case` in `_call()` in `tool_registry.py` eintragen
4. Falls User zugreifen darf: Namen in `USER_ALLOWED_TOOLS` eintragen

## Genre-Sortierer

`genre_sort_controller.py` sortiert Radarr-Filme in Genre-Unterordner – gesteuert durch die KI.

**Voraussetzungen:**
- Genre-Unterordner müssen im Radarr Root-Folder bereits existieren (z.B. `Action/`, `Horror/`, `Sci-Fi/`)
- Radarr-Container braucht Schreibzugriff auf diese Ordner

**Ablauf (zwei Tool-Call-Runden in agent.py):**
1. KI ruft `get_movies_for_genre_sort` auf → bekommt Filme mit TMDB-Genres + Overview + verfügbare Ordner
2. KI entscheidet pro Film das Hauptgenre und ruft `assign_movie_genres` mit allen Zuweisungen auf
3. Controller setzt neuen Pfad via Radarr API (`PUT /api/v3/movie/{id}?moveFiles=true`)
   → Radarr verschiebt die Dateien selbst, der Eintrag bleibt erhalten

**Warum Multi-Round nötig war:** Der alte `agent.py` machte nur einen Tool-Call-Durchlauf.
Für Genre-Sorting braucht man zwei Runden (Daten holen → zuweisen). Deshalb wurde `agent.py`
auf eine Schleife mit `MAX_TOOL_ROUNDS = 5` umgebaut.

**Nutzung:** Nur Admin. Beispiel-Nachricht: _"Sortiere alle Filme nach Genre"_ oder
_"Sortiere die nächsten 10 unsortierten Filme in Genre-Ordner"_

## Infrastructure

- Läuft als Docker Container auf Unraid
- Dienste intern erreichbar über `http://seedbox:PORT`
- Docker-Überwachung via Socket-Mount `/var/run/docker.sock`
- Unraid API Plugin muss auf dem Host installiert sein
- Jellyfin Webhook-URL: `http://seedbox:9000/webhook/jellyfin`

