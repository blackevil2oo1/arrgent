"""
logging_config.py – Zentrales Logging für den Seedbox-Bot.

Logs werden täglich rotiert und 30 Tage aufbewahrt.
Speicherort: /app/logs/bot.log (im Container) → via Docker-Volume auf dem Host.

Log-Level:
  INFO  – Alle wichtigen Ereignisse: Nachrichten, Tool-Calls, Antworten
  DEBUG – Vollständige Tool-Argumente und -Ergebnisse (detailliert)
  ERROR – Fehler mit vollem Traceback

Verwendung in anderen Modulen:
  import logging
  log = logging.getLogger("bot.modul")
  log.info("Nachricht")
"""

import logging
import logging.handlers
import os
from pathlib import Path

LOG_DIR = Path(os.getenv("LOG_DIR", "/app/logs"))

_FORMATTER = logging.Formatter(
    fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def setup_logging(debug: bool = False) -> logging.Logger:
    """
    Initialisiert das Logging-System. Muss genau einmal in main.py aufgerufen werden.

    debug=True → DEBUG-Level auch auf Konsole (für Entwicklung).
    debug=False → INFO auf Konsole, DEBUG nur in der Datei.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # ── Konsole (INFO) ────────────────────────────────────────────────────
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if debug else logging.INFO)
    console.setFormatter(_FORMATTER)
    root.addHandler(console)

    # ── Datei mit täglicher Rotation (30 Tage) ───────────────────────────
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=LOG_DIR / "bot.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(_FORMATTER)
    root.addHandler(file_handler)

    # ── Externe Libraries ruhig stellen ──────────────────────────────────
    for lib in ("httpx", "httpcore", "telegram", "openai", "uvicorn", "fastapi",
                "asyncio", "urllib3", "aiohttp"):
        logging.getLogger(lib).setLevel(logging.WARNING)

    log = logging.getLogger("bot.main")
    log.info("=" * 60)
    log.info(f"Logging gestartet – Logs unter: {LOG_DIR}/bot.log")
    log.info("=" * 60)
    return log
