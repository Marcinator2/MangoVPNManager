from __future__ import annotations


PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "window_top": "#e7eaee", "window_bottom": "#d9dee4",
        "surface": "#eef1f4", "surface_alt": "#e5e9ed",
        "surface_hover": "#dce6f5", "input": "#f2f4f6",
        "text": "#252a31", "muted": "#66707c", "border": "#c5ccd5",
        "border_strong": "#aab4c0", "selection": "#cfdeF5",
        "selection_text": "#17365f", "branch": "#e1e6ec",
        "ready": "#168150", "offline": "#bd3945", "pending": "#7b8592",
        "shadow": "#550f1824", "badge": "#dce8f8",
        "danger_surface": "#f2e4e5", "disabled_text": "#8c949e",
        "disabled_surface": "#d2d7dd", "disabled_border": "#b7bec7",
        "warning_surface": "#f2ead7", "warning_text": "#875f12",
    },
    "dark": {
        "window_top": "#292d32", "window_bottom": "#1f2226",
        "surface": "#30343a", "surface_alt": "#292d33",
        "surface_hover": "#35445a", "input": "#272b30",
        "text": "#e7eaee", "muted": "#abb3bf", "border": "#454b54",
        "border_strong": "#626b77", "selection": "#294b78",
        "selection_text": "#f1f6ff", "branch": "#373c43",
        "ready": "#65d49a", "offline": "#ff747e", "pending": "#9ba5b2",
        "shadow": "#99000000", "badge": "#263c5d",
        "danger_surface": "#4a3034", "disabled_text": "#6f7782",
        "disabled_surface": "#24272b", "disabled_border": "#353a41",
        "warning_surface": "#453d2c", "warning_text": "#f0c66a",
    },
}


def normalize_theme(theme: str) -> str:
    return theme if theme in PALETTES else "light"


def theme_color(theme: str, name: str) -> str:
    return PALETTES[normalize_theme(theme)][name]
