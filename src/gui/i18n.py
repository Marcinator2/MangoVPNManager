from __future__ import annotations

import re

from config.terminology import Terminology, normalize_terminology
from gui.i18n_de import DE
from gui.i18n_en import EN

TRANSLATIONS = {"en": EN, "de": DE}
_TOKENS = re.compile(r"@(location|router|device)_(singular|plural)@|\{(\d+)\}")


class Translator:
    def __init__(self, language: str = "en", terminology: Terminology | None = None) -> None:
        self.set_language(language)
        self.set_terminology(terminology)

    def set_language(self, language: str) -> None:
        self.language = language if language in TRANSLATIONS else "en"

    def set_terminology(self, terminology: Terminology | None) -> None:
        self.terminology = normalize_terminology(terminology)

    def term(self, role: str, form: str = "singular") -> str:
        default = TRANSLATIONS[self.language][f"term_{role}_{form}"]
        return self.terminology.get(self.language, {}).get(role, {}).get(form, default)

    def __call__(self, key: str, *args) -> str:
        template = TRANSLATIONS[self.language].get(key, key)
        # Resolve template tokens once; inserted text is never interpreted again.
        def substitute(match: re.Match) -> str:
            if match[1] is not None:
                return self.term(match[1], match[2])
            index = int(match[3])
            return str(args[index]) if index < len(args) else match[0]
        return _TOKENS.sub(substitute, template)

    def error(self, error: Exception) -> str:
        key = getattr(error, "translation_key", None)
        return self(key) if key else str(error)
