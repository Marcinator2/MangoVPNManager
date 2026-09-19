from __future__ import annotations

from gui.i18n_de import DE
from gui.i18n_en import EN


TRANSLATIONS = {"en": EN, "de": DE}


class Translator:
    def __init__(self, language: str = "en") -> None:
        self.language = language if language in TRANSLATIONS else "en"

    def set_language(self, language: str) -> None:
        self.language = language if language in TRANSLATIONS else "en"

    def __call__(self, key: str) -> str:
        return TRANSLATIONS[self.language].get(key, key)
