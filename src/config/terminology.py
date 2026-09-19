"""Validated display terminology, independent of router identities."""
from __future__ import annotations

import unicodedata

ROLES = ("location", "router", "device")
FORMS = ("singular", "plural")
MAX_TERM_LENGTH = 40
Terminology = dict[str, dict[str, dict[str, str]]]


def validate_term(value: str) -> str:
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise ValueError("Control characters are not allowed in display terms.")
    value = value.strip()
    if len(value) > MAX_TERM_LENGTH:
        raise ValueError("Display terms must contain at most 40 characters.")
    return value


def normalize_terminology(raw: object) -> Terminology:
    """Ignore malformed entries individually; empty fields use defaults."""
    result: Terminology = {}
    if not isinstance(raw, dict):
        return result
    for language in ("en", "de"):
        language_values = raw.get(language)
        if not isinstance(language_values, dict):
            continue
        for role in ROLES:
            forms = language_values.get(role)
            if not isinstance(forms, dict):
                continue
            for form in FORMS:
                value = forms.get(form)
                if not isinstance(value, str):
                    continue
                try:
                    value = validate_term(value)
                except ValueError:
                    continue
                if value:
                    result.setdefault(language, {}).setdefault(role, {})[form] = value
    return result
