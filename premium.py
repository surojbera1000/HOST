"""Telegram premium custom emoji (from a sticker pack like t.me/addemoji/tgiosicons).

Loads the pack once at startup and maps each emoji character to its custom_emoji_id.
Then a small HTML→entities converter lets us send messages where plain emojis are
shown as the pack's premium emoji (Premium users see them; others see the normal emoji).
Everything degrades gracefully: if the pack can't load, messages fall back to HTML.
"""
import config

_map: dict[str, str] = {}  # emoji char -> custom_emoji_id
_loaded = False


def load() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    pack = config.PREMIUM_EMOJI_PACK
    if not pack:
        return
    import tg  # lazy to avoid an import cycle

    try:
        res = tg.call("getStickerSet", {"name": pack})
    except Exception as e:  # noqa: BLE001
        print("[premium] could not load pack", pack, e)
        return
    for st in res.get("stickers", []):
        cid = st.get("custom_emoji_id")
        emo = st.get("emoji")
        # Only map single-scalar emojis (skip flags / ZWJ sequences) for safe offsets.
        if cid and emo and len(emo) == 1 and emo not in _map:
            _map[emo] = cid
    print(f"[premium] loaded {len(_map)} custom emoji from {pack}")


def enabled() -> bool:
    return bool(_map)


def _u16(ch: str) -> int:
    return 2 if ord(ch) > 0xFFFF else 1


def convert(html: str):
    """Turn our HTML (<b>, <code>, &amp;/&lt;/&gt;, plain emoji) into (text, entities).
    Returns None if premium is off."""
    if not _map:
        return None
    out: list[str] = []
    entities: list[dict] = []
    stack: list[tuple[str, int]] = []
    i, off, n = 0, 0, len(html)
    while i < n:
        if html.startswith("<b>", i):
            stack.append(("bold", off))
            i += 3
            continue
        if html.startswith("</b>", i):
            _close(stack, entities, "bold", off)
            i += 4
            continue
        if html.startswith("<code>", i):
            stack.append(("code", off))
            i += 6
            continue
        if html.startswith("</code>", i):
            _close(stack, entities, "code", off)
            i += 7
            continue
        if html.startswith("&amp;", i):
            ch, i = "&", i + 5
        elif html.startswith("&lt;", i):
            ch, i = "<", i + 4
        elif html.startswith("&gt;", i):
            ch, i = ">", i + 3
        else:
            ch, i = html[i], i + 1
        out.append(ch)
        w = _u16(ch)
        if ch in _map:
            entities.append({"type": "custom_emoji", "offset": off, "length": w, "custom_emoji_id": _map[ch]})
        off += w
    return "".join(out), entities


def _close(stack: list, entities: list, kind: str, off: int) -> None:
    for k in range(len(stack) - 1, -1, -1):
        if stack[k][0] == kind:
            start = stack.pop(k)[1]
            if off > start:
                entities.append({"type": kind, "offset": start, "length": off - start})
            return
