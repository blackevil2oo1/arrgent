"""
telegram_handler.py – Verbindet Telegram mit dem AI Layer.

Was hier passiert:
1. Bot empfängt Nachrichten aus erlaubten Chats
2. Hält Gesprächshistorie im Speicher (für Kontext bei Folgefragen)
3. Schickt die Nachricht an den AI Layer
4. Sendet die Antwort zurück an Telegram

Gesprächshistorie:
- Pro Chat wird eine Liste der letzten Nachrichten gespeichert
- So versteht ChatGPT Folgefragen wie "nimm die zweite Option"
- Geschichte wird nach 10 Nachrichten automatisch gekürzt
"""

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from html import escape as escape_html

import io
import logging
import time
import config
from ai.agent import process_message, client as openai_client
from controllers.book_controller import _search_cache, _search_cache_ts, BookController

log = logging.getLogger("bot.handler")

_book_ctrl = BookController()

# Für Hörbücher: zwischenspeichern welches Suchergebnis gewählt wurde,
# bis der User auch die Bibliothek gewählt hat.
# Format: { chat_id: {"entry": {...}, "libraries": [...]} }
_pending_audiobook: dict[int, dict] = {}

# Gesprächshistorie pro Chat (im RAM, wird bei Neustart geleert)
# Format: { chat_id: [ {role, content}, ... ] }
_conversation_history: dict[int, list] = {}

MAX_HISTORY = 10  # Letzte X Nachrichten im Gedächtnis behalten


def _get_history(chat_id: int) -> list:
    return _conversation_history.get(chat_id, [])


def _add_to_history(chat_id: int, role: str, content: str):
    if chat_id not in _conversation_history:
        _conversation_history[chat_id] = []

    _conversation_history[chat_id].append({"role": role, "content": content})

    # Älteste Einträge entfernen wenn zu lang
    if len(_conversation_history[chat_id]) > MAX_HISTORY:
        _conversation_history[chat_id] = _conversation_history[chat_id][-MAX_HISTORY:]


_HILFE_TEXT = """<b>Was kann ich für dich tun?</b>

🎬 <b>Filme</b>
„Suche Inception" – Film suchen
„Lade Inception herunter" – Film herunterladen

📺 <b>Serien</b>
„Suche Breaking Bad" – Serie suchen
„Lade Breaking Bad herunter" – Serie herunterladen

📚 <b>Bücher &amp; Hörbücher</b>
„Suche das Buch Harry Potter"
„Hörbuch Der Herr der Ringe herunterladen"

🆕 <b>Neuheiten</b>
„Was gibt es Neues?" – Letzte Downloads anzeigen

Schreib einfach auf Deutsch, ich verstehe dich!"""


async def handle_hilfe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Antwortet auf /hilfe und /start mit einer Übersicht aller Funktionen."""
    if not update.message:
        return
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    await update.message.reply_text(_HILFE_TEXT, parse_mode=ParseMode.HTML)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wird aufgerufen wenn der Bot eine Nachricht empfängt."""
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    text = update.message.text

    # Prüfen ob die Nachricht aus einem erlaubten Chat kommt
    if not config.is_allowed_chat(chat_id):
        log.warning(f"[chat={chat_id}] Nachricht aus unbekanntem Chat ignoriert")
        await update.message.reply_text("Ich bin nicht für diesen Chat konfiguriert.")
        return

    log.info(f"[chat={chat_id}] Nachricht: {text[:200]}")

    # "Schreibt..." Indikator anzeigen während verarbeitet wird
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    except Exception:
        pass

    # Pending-Hörbuch-Auswahl automatisch abbrechen wenn User etwas anderes schreibt
    if chat_id in _pending_audiobook and not text.strip().isdigit():
        log.info(f"[chat={chat_id}] Pending-Hörbuch abgebrochen (neue Eingabe: '{text[:50]}')")
        _pending_audiobook.pop(chat_id, None)

    # Schritt 2 Hörbuch: User wählt Bibliothek → Download starten
    if text.strip().isdigit() and chat_id in _pending_audiobook:
        lib_index = int(text.strip())
        pending = _pending_audiobook.pop(chat_id)
        libraries = pending["libraries"]
        entry = pending["entry"]
        if 1 <= lib_index <= len(libraries):
            lib = libraries[lib_index - 1]
            try:
                result = _book_ctrl.download_book_by_url(
                    nzb_url=entry["url"],
                    title=entry["title"],
                    library_id=lib["id"],
                    book_type="audiobook",
                    chat_id=chat_id,
                )
                if result.get("success"):
                    log.info(f"[chat={chat_id}] Hörbuch-Download gestartet: '{entry['title']}' → Bibliothek '{lib['name']}'")
                    reply = f"✓ <b>{escape_html(entry['title'])}</b> wird in <b>{escape_html(lib['name'])}</b> heruntergeladen."
                    await update.message.reply_text(reply, parse_mode=ParseMode.HTML)
                    _add_to_history(chat_id, "user", text)
                    _add_to_history(chat_id, "assistant", f"'{entry['title']}' wird in '{lib['name']}' heruntergeladen.")
                else:
                    log.warning(f"[chat={chat_id}] Hörbuch-Download fehlgeschlagen: {result.get('message')}")
                    await update.message.reply_text(
                        f"Fehler: {escape_html(result.get('message', 'Unbekannter Fehler'))}",
                        parse_mode=ParseMode.HTML,
                    )
            except Exception as e:
                log.error(f"[chat={chat_id}] Hörbuch-Download Exception: {e}", exc_info=True)
                await update.message.reply_text("Verbindungsfehler. Bitte nochmal versuchen.")
        else:
            await update.message.reply_text(
                f"Ungültige Auswahl. Bitte eine Nummer zwischen 1 und {len(libraries)} eingeben."
            )
        return

    # Schritt 1: User wählt aus Buch-/Hörbuch-Suchergebnissen
    _CACHE_TTL = 1800  # 30 Minuten
    cache_valid = (
        text.strip().isdigit()
        and chat_id in _search_cache
        and bool(_search_cache[chat_id])
        and (time.time() - _search_cache_ts.get(chat_id, 0)) < _CACHE_TTL
    )
    if cache_valid:
        index = int(text.strip())
        cached = _search_cache[chat_id]
        if 1 <= index <= len(cached):
            entry = cached[index - 1]

            if entry["book_type"] == "ebook":
                # Ebook: direkt downloaden
                try:
                    result = _book_ctrl.download_book(
                        index=index,
                        title=entry["title"],
                        book_type="ebook",
                        chat_id=chat_id,
                    )
                    if result.get("success"):
                        _search_cache.pop(chat_id, None)
                        log.info(f"[chat={chat_id}] Ebook-Download gestartet: '{entry['title']}'")
                        reply = f"✓ <b>{escape_html(entry['title'])}</b> wird heruntergeladen."
                        await update.message.reply_text(reply, parse_mode=ParseMode.HTML)
                        _add_to_history(chat_id, "user", text)
                        _add_to_history(chat_id, "assistant", f"'{entry['title']}' wird heruntergeladen.")
                    else:
                        log.warning(f"[chat={chat_id}] Ebook-Download fehlgeschlagen: {result.get('message')}")
                        await update.message.reply_text(
                            f"Fehler: {escape_html(result.get('message', 'Unbekannter Fehler'))}",
                            parse_mode=ParseMode.HTML,
                        )
                except Exception as e:
                    log.error(f"[chat={chat_id}] Ebook-Download Exception: {e}", exc_info=True)
                    await update.message.reply_text("Verbindungsfehler. Bitte nochmal versuchen.")

            else:
                # Hörbuch: erst Bibliotheken abfragen, dann auf zweite Auswahl warten
                try:
                    libraries = _book_ctrl.get_audiobook_libraries()
                    _search_cache.pop(chat_id, None)
                    if not libraries:
                        await update.message.reply_text(
                            "Keine Audiobookshelf-Bibliotheken verfügbar. Bitte den Admin kontaktieren."
                        )
                        return
                    _pending_audiobook[chat_id] = {"entry": entry, "libraries": libraries}
                    lib_list = "\n".join(
                        f"{i+1}. {lib['name']}" for i, lib in enumerate(libraries)
                    )
                    await update.message.reply_text(
                        f"In welche Bibliothek soll <b>{escape_html(entry['title'])}</b>?\n\n{lib_list}",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception as e:
                    log.error(f"[chat={chat_id}] Bibliotheken-Abruf Exception: {e}", exc_info=True)
                    await update.message.reply_text("Fehler beim Abrufen der Bibliotheken.")
            return
        else:
            await update.message.reply_text(
                f"Ungültige Auswahl. Bitte eine Nummer zwischen 1 und {len(cached)} eingeben."
            )
            return

    # Normale KI-Verarbeitung
    history = list(_get_history(chat_id))
    _add_to_history(chat_id, "user", text)

    try:
        response = await process_message(text, history, chat_id=chat_id)
        _add_to_history(chat_id, "assistant", response)
        try:
            await update.message.reply_text(response, parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(response)
    except Exception as e:
        error_type = type(e).__name__
        if "Timeout" in error_type or "timeout" in str(e).lower():
            reply = "Die KI-API antwortet gerade zu langsam. Bitte in ein paar Sekunden nochmal versuchen."
        else:
            reply = "Es ist ein Fehler aufgetreten. Bitte nochmal versuchen."
        await update.message.reply_text(reply)
        log.error(f"[chat={chat_id}] handle_message Fehler: [{error_type}] {e}", exc_info=True)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Transkribiert Sprachnachrichten mit Whisper und verarbeitet sie wie Text."""
    if not update.message or not update.message.voice:
        return

    chat_id = update.effective_chat.id

    if not config.is_allowed_chat(chat_id):
        return

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        voice_file = await update.message.voice.get_file()
        audio_bytes = await voice_file.download_as_bytearray()

        audio_buffer = io.BytesIO(bytes(audio_bytes))
        audio_buffer.name = "voice.ogg"

        transcript = await openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_buffer,
            language="de",
        )
        text = transcript.text.strip()

        if not text:
            await update.message.reply_text("Ich konnte die Sprachnachricht leider nicht verstehen.")
            return

        log.info(f"[chat={chat_id}] Sprachnachricht transkribiert: {text[:200]}")
        await update.message.reply_text(f"🎤 <i>{escape_html(text)}</i>", parse_mode=ParseMode.HTML)

        # Transkription wie normale Textnachricht verarbeiten
        update.message.text = text
        await handle_message(update, context)

    except Exception as e:
        log.error(f"[chat={chat_id}] Whisper-Transkription Fehler: {e}", exc_info=True)
        await update.message.reply_text("Fehler bei der Spracherkennung. Bitte nochmal versuchen.")


async def send_notification(bot, chat_id: int, message: str):
    """
    Sendet eine proaktive Benachrichtigung an einen Chat.
    Wird von Webhooks aufgerufen.
    """
    await bot.send_message(chat_id=chat_id, text=message)


def create_application() -> Application:
    """Erstellt und konfiguriert die Telegram Bot Application."""
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler(["hilfe", "start", "help"], handle_hilfe))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    return app
