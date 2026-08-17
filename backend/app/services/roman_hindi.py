import re
import unicodedata

try:
    from indic_transliteration import sanscript
    from indic_transliteration.sanscript import transliterate
except ImportError:  # capability is checked when Roman Hindi is requested
    sanscript = None
    transliterate = None

DEVANAGARI = re.compile(r"[\u0900-\u097f]")
TOKEN = re.compile(r"[\u0900-\u097f]+|[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*|[^\w\s]+", re.UNICODE)

COMMON = {
    "kyaa": "kya", "main": "main", "hoo~": "hoon", "haan~": "haan",
    "haa~": "haan", "are": "arre", "yaar": "yaar", "sahee": "sahi",
    "naheen": "nahi", "nahee": "nahi", "men": "mein", "mein": "mein", "hain": "hain",
    "hai": "hai", "karoo~": "karoon", "dekhoo~": "dekhoon",
    "oopar": "upar", "injiniyaring": "engineering", "injiniering": "engineering",
}


def _naturalize(value: str) -> str:
    replacements = {
        "ā": "aa", "ī": "ee", "ū": "oo", "ṛ": "ri", "ṝ": "ri",
        "ṃ": "n", "ṁ": "n", "ṅ": "n", "ñ": "n", "ṇ": "n",
        "ṭ": "t", "ḍ": "d", "ś": "sh", "ṣ": "sh", "ḥ": "h", "~": "n",
    }
    value = "".join(replacements.get(ch, ch) for ch in value.casefold())
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    # Hindi's written inherent schwa is commonly silent at the end of a word.
    if len(value) > 2 and value.endswith("a") and not value.endswith(("aa", "ia")):
        value = value[:-1]
    return COMMON.get(value, value)


def romanize_word(value: str) -> str:
    if not DEVANAGARI.search(value): return value
    if transliterate is None or sanscript is None:
        raise RuntimeError("Roman Hindi captions require indic-transliteration. Reinstall backend requirements.")
    return _naturalize(transliterate(value, sanscript.DEVANAGARI, sanscript.IAST))


def romanize_hindi(text: str) -> str:
    """Transliterate spoken Hindi to readable Latin-script Hinglish without translating English."""
    pieces = TOKEN.findall(text)
    output = ""
    for piece in pieces:
        converted = romanize_word(piece)
        if output and converted not in ",.!?;:।…)]}" and output[-1] not in " ([{\n": output += " "
        output += converted
    return output.replace(" ।", ".").strip()


def add_roman_display_text(segments: list[dict], enabled: bool) -> list[dict]:
    if not enabled: return segments
    for segment in segments:
        segment["source_text"] = segment.get("text", "")
        segment["display_text"] = romanize_hindi(str(segment.get("text", "")))
        for word in segment.get("words", []):
            word["source_text"] = word.get("text", "")
            word["display_text"] = romanize_word(str(word.get("text", "")))
    return segments
