"""Search-only normalization. Original text is never modified."""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Iterable

WORD_RE = re.compile(r"[^\W_]+(?:['’ʼ-][^\W_]+)*", re.UNICODE)
SUBWORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
# Grouped integer or decimal. Spaces are permitted only as 3-digit group separators.
NUMBER_RE = re.compile(
    r"(?<![\w])(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)(?:[.,]\d+)?(?![\w])",
    re.UNICODE,
)


class Morphology:
    """Prefer pymorphy3; use NLTK Snowball Russian stemmer as a local fallback."""
    def __init__(self) -> None:
        self.engine = "pymorphy3"
        try:
            import pymorphy3  # type: ignore
            self._analyzer = pymorphy3.MorphAnalyzer(lang="ru")
            self._stemmer = None
        except ImportError:
            try:
                from nltk.stem.snowball import RussianStemmer  # type: ignore
                self._analyzer = None
                self._stemmer = RussianStemmer()
                self.engine = "nltk-snowball-fallback"
            except ImportError as exc:
                raise RuntimeError("Install pymorphy3 and pymorphy3-dicts-ru, or nltk for fallback stemming") from exc

    def normalize_word(self, word: str) -> str:
        normalized = unicodedata.normalize("NFC", word).casefold()
        if not any("а" <= ch <= "я" or ch == "ё" for ch in normalized):
            return normalized
        if self._analyzer is not None:
            try:
                return self._analyzer.parse(normalized)[0].normal_form
            except Exception:
                return normalized
        try:
            return self._stemmer.stem(normalized)
        except Exception:
            return normalized

    def normalize_text(self, text: str) -> str:
        words: list[str] = []
        for token in WORD_RE.findall(unicodedata.normalize("NFC", text)):
            # Hyphens/apostrophes are boundaries for lexical search; preserve parts.
            parts = SUBWORD_RE.findall(token)
            words.extend(self.normalize_word(part) for part in parts)
        return " ".join(words)


def tokenize(text: str) -> list[str]:
    return [part.casefold() for token in WORD_RE.findall(unicodedata.normalize("NFC", text)) for part in SUBWORD_RE.findall(token)]


def alias_key(text: str) -> str:
    return " ".join(tokenize(text))


def canonical_number(value: str) -> str | None:
    """Return an exact decimal key; grouped-space integers collapse to digits."""
    compact = value.replace(" ", "").replace("\u00a0", "").replace("\u202f", "")
    # A single comma or dot followed by 1-2 digits is treated as decimal notation.
    # For 3 digits after a separator, this implementation treats it as decimal too;
    # grouped thousands are expressed with spaces to avoid locale ambiguity.
    if compact.count(",") + compact.count(".") > 1:
        return None
    compact = compact.replace(",", ".")
    try:
        number = Decimal(compact)
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    normalized = number.normalize()
    if normalized == normalized.to_integral_value():
        return str(normalized.quantize(Decimal(1)))
    return format(normalized, "f")


def extract_numbers(text: str) -> list[tuple[str, str, int, int]]:
    """(canonical_key, surface, start, end) for valid numeric tokens."""
    found: list[tuple[str, str, int, int]] = []
    for match in NUMBER_RE.finditer(text):
        key = canonical_number(match.group(0))
        if key is not None:
            found.append((key, match.group(0), match.start(), match.end()))
    return found


def _non_numeric_query_tokens(text: str) -> list[str]:
    """Return lexical tokens only; numeric expressions are searched by exact value."""
    lexical: list[str] = []
    for match in WORD_RE.finditer(unicodedata.normalize("NFC", text)):
        parts = SUBWORD_RE.findall(match.group(0))
        # Do not put digits into FTS5: a grouped number must match as one value,
        # not as unrelated digit tokens in the same document.
        if all(part.isdigit() for part in parts):
            continue
        lexical.extend(part.casefold() for part in parts if not part.isdigit())
    return lexical


def build_fts_query(text: str) -> str:
    """Build safe exact-channel FTS5 query restricted to original-text columns."""
    parts = list(dict.fromkeys(_non_numeric_query_tokens(text)))
    if not parts:
        return ""
    columns = ("title_original", "path_original", "heading_original", "raw_text")
    clauses = []
    for part in parts:
        quoted = f'"{part.replace(chr(34), chr(34) * 2)}"'
        clauses.append("(" + " OR ".join(f"{column} : {quoted}" for column in columns) + ")")
    return " AND ".join(clauses)


def build_morph_fts_query(text: str, morphology: Morphology) -> str:
    """Build safe morphology query restricted to lemma/stem columns."""
    parts = [morphology.normalize_word(p) for p in _non_numeric_query_tokens(text)]
    parts = list(dict.fromkeys(p for p in parts if p))
    if not parts:
        return ""
    columns = ("title_lemmas", "heading_lemmas", "raw_lemmas")
    clauses = []
    for part in parts:
        quoted = f'"{part.replace(chr(34), chr(34) * 2)}"'
        clauses.append("(" + " OR ".join(f"{column} : {quoted}" for column in columns) + ")")
    return " AND ".join(clauses)
