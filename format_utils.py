"""Formatting helpers."""


def inr(paise: int) -> str:
    return "\u20b9" + f"{paise / 100:,.2f}"


def countdown(ms_left: int) -> str:
    s = max(0, ms_left // 1000)
    return f"{s // 60}:{s % 60:02d}"


def esc(s) -> str:
    return str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_FLAGS = {
    "india": "\U0001F1EE\U0001F1F3",
    "indonesia": "\U0001F1EE\U0001F1E9",
    "usa": "\U0001F1FA\U0001F1F8",
    "usa (virtual)": "\U0001F1FA\U0001F1F8",
    "usa (2)": "\U0001F1FA\U0001F1F8",
    "russia": "\U0001F1F7\U0001F1FA",
    "china": "\U0001F1E8\U0001F1F3",
    "philippines": "\U0001F1F5\U0001F1ED",
    "vietnam": "\U0001F1FB\U0001F1F3",
    "united kingdom": "\U0001F1EC\U0001F1E7",
    "england": "\U0001F1EC\U0001F1E7",
    "chile": "\U0001F1E8\U0001F1F1",
    "colombia": "\U0001F1E8\U0001F1F4",
    "south africa": "\U0001F1FF\U0001F1E6",
    "brazil": "\U0001F1E7\U0001F1F7",
    "nigeria": "\U0001F1F3\U0001F1EC",
    "kenya": "\U0001F1F0\U0001F1EA",
    "pakistan": "\U0001F1F5\U0001F1F0",
    "bangladesh": "\U0001F1E7\U0001F1E9",
    "sri lanka": "\U0001F1F1\U0001F1F0",
    "myanmar": "\U0001F1F2\U0001F1F2",
    "thailand": "\U0001F1F9\U0001F1ED",
    "malaysia": "\U0001F1F2\U0001F1FE",
    "cambodia": "\U0001F1F0\U0001F1ED",
    "poland": "\U0001F1F5\U0001F1F1",
    "ukraine": "\U0001F1FA\U0001F1E6",
    "kazakhstan": "\U0001F1F0\U0001F1FF",
    "mexico": "\U0001F1F2\U0001F1FD",
    "argentina": "\U0001F1E6\U0001F1F7",
    "hong kong": "\U0001F1ED\U0001F1F0",
    "nepal": "\U0001F1F3\U0001F1F5",
    "egypt": "\U0001F1EA\U0001F1EC",
    "morocco": "\U0001F1F2\U0001F1E6",
}


def flag(name: str) -> str:
    return _FLAGS.get(name.strip().lower(), "\U0001F310")
