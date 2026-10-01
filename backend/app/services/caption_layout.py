import re
from dataclasses import dataclass
from typing import Any

END = re.compile(r"[.!?।…]+$")
SOFT_END = re.compile(r"[,;:]$")
CONJUNCTIONS = {"and", "but", "because", "so", "then", "or", "aur", "lekin", "par",
                "kyunki", "toh", "phir", "magar", "ya", "isliye"}
CAPTION_PAUSE_BREAK_SECONDS = .35


@dataclass(frozen=True)
class CaptionCard:
    start: float
    end: float
    words: tuple[dict[str, Any], ...]
    lines: tuple[str, ...]


def _visual_width(text: str) -> float:
    """Approximate measured Latin display width; narrow glyphs do not count as full cells."""
    return sum(.42 if ch in "ilI1.,'|!" else 1.25 if ch in "MW@%" else 1.0 for ch in text)


def _line_len(words: list[str]) -> float:
    return _visual_width(" ".join(words))


def _wrap(words: list[str], max_chars: int) -> tuple[str, ...]:
    if not words:
        return ()
    best: tuple[int, int] | None = None
    for split in range(1, len(words)):
        left, right = _line_len(words[:split]), _line_len(words[split:])
        overflow = max(0, left - max_chars) + max(0, right - max_chars)
        boundary = words[split].casefold().strip(",.!?;:")
        linguistic_bonus = 20 if boundary in CONJUNCTIONS else 0
        punctuation_bonus = 6 if SOFT_END.search(words[split-1]) else 0
        score = overflow * 100 + abs(left - right) - linguistic_bonus - punctuation_bonus
        if best is None or score < best[0]:
            best = (score, split)
    if _line_len(words) <= max_chars or not best:
        return (" ".join(words),)
    split = best[1]
    return (" ".join(words[:split]), " ".join(words[split:]))


def build_caption_cards(words: list[dict[str, Any]], max_chars: int = 28,
                        max_words: int = 7, max_duration: float = 3.2,
                        pause_break: float = CAPTION_PAUSE_BREAK_SECONDS) -> list[CaptionCard]:
    """Create readable phrase cards from aligned words; never emits >2 lines."""
    valid = [w for w in words if str(w.get("text", "")).strip()
             and float(w.get("end", 0)) > float(w.get("start", 0))]
    cards: list[CaptionCard] = []
    current: list[dict[str, Any]] = []
    for word in valid:
        if current:
            pause = float(word["start"]) - float(current[-1]["end"])
            projected = [str(w["text"]).strip() for w in current + [word]]
            projected_lines = _wrap(projected, max_chars)
            too_long = len(projected) > max_words or sum(map(len, projected)) + len(projected) - 1 > max_chars * 2
            # Raw character count can say a phrase fits across two lines even
            # when the renderer's visual-width metric cannot split it safely.
            # Break before the new word instead of failing the whole export.
            too_wide = any(_visual_width(line) > max_chars for line in projected_lines)
            too_slow = float(word["end"]) - float(current[0]["start"]) > max_duration
            if pause >= pause_break or too_long or too_wide or too_slow or END.search(str(current[-1]["text"])):
                texts = [str(w["text"]).strip() for w in current]
                cards.append(CaptionCard(float(current[0]["start"]), float(current[-1]["end"]),
                                         tuple(current), _wrap(texts, max_chars)))
                current = []
        current.append(word)
    if current:
        texts = [str(w["text"]).strip() for w in current]
        cards.append(CaptionCard(float(current[0]["start"]), float(current[-1]["end"]),
                                 tuple(current), _wrap(texts, max_chars)))
    return cards


def validate_cards(cards: list[CaptionCard], max_chars: int = 28) -> list[str]:
    errors: list[str] = []
    for index, card in enumerate(cards):
        if card.end <= card.start: errors.append(f"card_{index}_invalid_time")
        if len(card.lines) > 2: errors.append(f"card_{index}_too_many_lines")
        # Keep validation consistent with the renderer's actual line-break
        # metric. Raw code-point count wrongly rejects narrow Latin glyph runs.
        if any(_visual_width(line) > max_chars for line in card.lines): errors.append(f"card_{index}_overflow")
        cps = sum(len(line) for line in card.lines) / max(card.end - card.start, .01)
        if cps > 24: errors.append(f"card_{index}_too_fast")
    return errors
