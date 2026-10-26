"""Shared language choices and paths for generated summary variants."""
from __future__ import annotations

from pathlib import Path
import re

SUMMARY_LANGUAGE_NAMES: dict[str, str] = {
    "fr": "français",
    "en": "anglais",
    "de": "allemand",
    "it": "italien",
    "es": "espagnol",
    "pt": "portugais",
    "nl": "néerlandais",
}
SUMMARY_LANGUAGE_CODES: tuple[str, ...] = ("auto", *SUMMARY_LANGUAGE_NAMES.keys())
TRANSLATION_LANGUAGE_CODES: tuple[str, ...] = tuple(SUMMARY_LANGUAGE_NAMES.keys())


# Language-specific function words that are useful to identify the language of a
# transcript without installing a second NLP model. Shared words are intentionally
# avoided so closely related languages are less likely to win by accident.
_LANGUAGE_MARKERS: dict[str, frozenset[str]] = {
    "fr": frozenset("les des une est sont avec pas pour nous vous mais donc cette parce leur leurs ils elles être avoir ont fait dans chez depuis alors encore très quand quoi comment pourquoi elle lui été était étaient était".split()),
    "en": frozenset("the and is are was were have has not but with from they it we you this that their then because which would could should there these those been being when what how your our about can do does did will".split()),
    "de": frozenset("der die das und ist sind nicht mit für eine ein aber auch ich wir sie zu dass werden kann einen einem wird haben hat war sich ihr ihre weil wenn wie was wer wo warum können wurde als nach noch".split()),
    "it": frozenset("gli che è sono non per con una del della nel alla come questo questa anche però quindi dove perché ha hanno essere stato delle dagli nelle degli degli quale quando perché loro noi voi".split()),
    "es": frozenset("los las y es para con no pero también está son hay una unos porque esto eso muy más al se tiene ser estar fue era puede pueden ustedes ellas ellos nosotros desde hasta como dónde cuándo quién".split()),
    "pt": frozenset("os as e é um uma não para com mas também está são isso porque mais muito vocês ele ela foi ser ter do da dos ao pelo pela eles elas nós desde como quando quem onde pode foram".split()),
    "nl": frozenset("het een en van dat op voor met niet zijn maar ook deze dit hij zij wij jullie hun was naar wordt hebben als omdat kunnen er bij wel nog geen welke waarom wat wie waar wanneer jullie".split()),
}

def detect_transcript_language(text: str) -> str | None:
    """Conservatively identify a dominant supported language from transcript text.

    This lightweight detector is used only for static headings; generation prompts
    still ask the model to follow the transcript itself. Short or ambiguous samples
    return None rather than pretending a language was identified with certainty.
    """
    source = str(text or "")
    if len(source) > 15000:
        middle = len(source) // 2
        source = source[:5000] + "\n" + source[middle - 2500:middle + 2500] + "\n" + source[-5000:]
    tokens = re.findall(r"[a-zà-ÿ]+", source.casefold())
    if len(tokens) < 35:
        return None
    counts = {code: sum(token in markers for token in tokens) for code, markers in _LANGUAGE_MARKERS.items()}
    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    best_code, best_score = ranked[0]
    runner_up = ranked[1][1]
    if best_score < max(4, int(len(tokens) * 0.012)) or best_score - runner_up < 2:
        return None
    return best_code


def summary_language_instruction(language: str | None) -> str:
    """Return a clear target-language instruction suitable for local LLM prompts."""
    code = (language or "auto").strip().casefold()
    if code == "auto":
        return (
            "dans la même langue dominante que la transcription originale. Ne traduis pas la source ; "
            "garde sa langue, même si les consignes techniques sont rédigées en français."
        )
    name = SUMMARY_LANGUAGE_NAMES.get(code)
    if name is None:
        raise ValueError(f"Langue de résumé non prise en charge : {language}")
    return f"en {name} (code {code})"


def summary_translation_path(folder: str | Path, language: str) -> Path:
    """Return the safe path of one translation, restricted to supported language codes."""
    code = language.strip().casefold()
    if code not in TRANSLATION_LANGUAGE_CODES:
        raise ValueError(f"Langue de traduction non prise en charge : {language}")
    return Path(folder).resolve() / "summary" / "translations" / f"{code}.md"


def available_summary_translations(folder: str | Path) -> list[str]:
    """List existing translated-summary variants without trusting arbitrary filenames."""
    directory = Path(folder).resolve() / "summary" / "translations"
    if not directory.is_dir():
        return []
    return sorted(
        path.stem for path in directory.glob("*.md")
        if path.is_file() and path.stem in TRANSLATION_LANGUAGE_CODES
    )
