"""
agent.py – Der AI Layer. Herzstück des Systems.

Was dieser Layer macht:
1. Nimmt eine Textnachricht entgegen
2. Schickt sie mit den verfügbaren Tool-Definitionen an ChatGPT
3. ChatGPT entscheidet welche Funktion aufgerufen werden soll
4. tool_registry.dispatch() führt die Funktion aus
5. Das Ergebnis geht zurück an ChatGPT
6. ChatGPT kann weitere Tools aufrufen oder eine Antwort formulieren
7. Schleife läuft bis ChatGPT keine Tools mehr aufruft (max. MAX_TOOL_ROUNDS)

Was dieser Layer NICHT macht:
- Keine direkte Kommunikation mit Radarr, Sonarr, etc.
- Keine Telegram-Logik
- Keine Business-Logik
"""

import json
import logging
from openai import AsyncOpenAI
import config
from ai.tool_registry import get_tools, dispatch
from ai.intent_classifier import classify, filter_tools

log = logging.getLogger("bot.agent")

# Timeout für OpenAI API-Aufrufe in Sekunden.
OPENAI_TIMEOUT = 20.0

client = AsyncOpenAI(api_key=config.OPENAI_API_KEY, timeout=OPENAI_TIMEOUT)

# Maximale Tool-Call-Runden pro Nachricht (verhindert Endlosschleifen)
MAX_TOOL_ROUNDS = 5

SYSTEM_PROMPT = """Du bist ein freundlicher Assistent der eine Medienserver-Sammlung verwaltet.
Du hilfst dabei Filme, Serien, Bücher und Hörbücher zu finden und herunterzuladen.
Antworte immer auf Deutsch. Sei präzise, freundlich und verständlich – die Nutzer haben keine technischen Kenntnisse.
Verwende HTML-Formatierung für bessere Lesbarkeit: <b>fett</b> für Titel und wichtige Informationen.
Erzeuge niemals Shell-Befehle, Systembefehle oder ausführbaren Code.
Verwende ausschließlich die bereitgestellten Tools.

FILM-ABLAUF:
1. search_movie aufrufen → Treffer nummeriert anzeigen (Titel + Jahr).
2. User wählt einen Film → get_radarr_quality_profiles aufrufen → Profile einfach erklären (z.B. "HD (1080p)" oder "4K").
3. User wählt Qualität → add_movie mit der 'id' aus dem Profilergebnis aufrufen (NICHT die Listennummer als ID).

SERIEN-ABLAUF:
1. search_series aufrufen → Treffer nummeriert anzeigen (Titel + Jahr).
2. User wählt eine Serie → get_sonarr_quality_profiles aufrufen → Profile einfach erklären.
3. User wählt Qualität → add_series mit der 'id' aus dem Profilergebnis aufrufen (NICHT die Listennummer als ID).

BUCH/HÖRBUCH-ABLAUF – diese Reihenfolge exakt einhalten:
1. User sucht Buch/Hörbuch → search_book EINMAL aufrufen → Ergebnisse nummeriert anzeigen → WARTEN.
2. User nennt eine Zahl → das ist die Auswahl. NICHT erneut suchen, NICHT nach Bestätigung fragen.
3. Ebook: sofort download_book aufrufen. Fertig.
4. Hörbuch: get_book_libraries aufrufen → Bibliotheken nummeriert anzeigen → WARTEN bis User Bibliothek wählt → dann download_book.
BUCH-TYP ERKENNUNG: "Buch", "Ebook", "E-Book" → book_type="ebook". "Hörbuch", "Audiobook", "hör" → book_type="audiobook". Bei Unklarheit frage kurz nach.

Wichtige Regeln:
- Frage nie zweimal nach derselben Information.
- Zeige bei Qualitätsprofilen immer die Namen (nicht die IDs), nutze die 'id' nur intern beim API-Aufruf.
- Wenn ein Suchergebnis 'already_in_radarr: true' oder 'already_in_sonarr: true' enthält, oder die Antwort 'already_exists: true' hat: teile dem User mit, dass der Titel bereits in der Sammlung ist. add_movie oder add_series NICHT aufrufen.
- Wenn eine Suche 0 Ergebnisse zurückgibt: versuche es automatisch mit dem englischen Originaltitel (z.B. "Der Herr der Ringe" → "The Lord of the Rings"). Erkläre dem User dass du den Originaltitel versuchst.
- Bei Fehlern: erkläre das Problem einfach und schlage vor, es später nochmal zu versuchen.
- Bei get_recent_media: Zeige Filme und Serien als zwei getrennte Listen. Bei Serien nur den Seriennamen, keine Episodendetails.
"""


async def process_message(text: str, conversation_history: list, chat_id: int = 0) -> str:
    """
    Verarbeitet eine Nachricht und gibt eine Antwort zurück.

    text: Die Nachricht des Users
    conversation_history: Bisherige Nachrichten dieser Konversation (für Kontext)
    """
    all_tools = get_tools()

    # Intent klassifizieren → Tool-Liste eingrenzen (spart Token)
    intent = classify(text)
    tools = filter_tools(intent, all_tools)
    tool_names = [t["function"]["name"] for t in tools]

    log.info(f"[chat={chat_id}] {text[:200]}")
    log.info(f"[chat={chat_id}] Intent: {intent.value} | Tools: {tool_names}")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": text})

    for round_num in range(MAX_TOOL_ROUNDS):
        response = await client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        message = response.choices[0].message

        # Keine weiteren Tool-Calls → ChatGPT hat eine Antwort formuliert
        if not message.tool_calls:
            log.info(f"[chat={chat_id}] Antwort (Runde {round_num + 1}): {(message.content or '')[:300]}")
            return message.content

        messages.append(message)

        for tool_call in message.tool_calls:
            function_name = tool_call.function.name
            try:
                arguments = json.loads(tool_call.function.arguments)
            except (json.JSONDecodeError, ValueError) as e:
                log.error(f"[chat={chat_id}] Ungültige Tool-Argumente für {function_name}: {e}")
                return "Es ist ein interner Fehler aufgetreten. Bitte versuche es erneut."

            args_short = json.dumps(arguments, ensure_ascii=False)[:300]
            log.info(f"[chat={chat_id}] Tool-Call: {function_name}({args_short})")

            result = dispatch(function_name, arguments, chat_id=chat_id)

            log.debug(f"[chat={chat_id}] Tool-Result: {result[:500]}")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

    log.warning(f"[chat={chat_id}] MAX_TOOL_ROUNDS ({MAX_TOOL_ROUNDS}) erreicht – erzwinge Abschluss")
    final_response = await client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=messages,
    )
    final_text = final_response.choices[0].message.content if final_response.choices else None
    log.info(f"[chat={chat_id}] Abschluss-Antwort: {(final_text or '')[:300]}")
    return final_text or "Ich konnte keine Antwort generieren. Bitte versuche es erneut."
