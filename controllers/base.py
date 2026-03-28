"""
base.py – Abstrakte Basisklasse für alle Controller.

Jeder Controller erbt von BaseController und muss dadurch
eine einheitliche Struktur haben. Das macht es einfach,
neue Controller hinzuzufügen.
"""

from abc import ABC


class BaseController(ABC):
    """
    Basisklasse für alle Controller.

    Jeder Controller:
    - bekommt seine URL und API-Key aus config.py
    - hat einen Namen der in Fehlermeldungen erscheint
    - stellt seine Funktionen als normale Python-Methoden bereit
    """

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict:
        """Standard API-Header – wird von den meisten Controllern verwendet."""
        return {"X-Api-Key": self.api_key, "Content-Type": "application/json"}
