"""Step 5 - response validation: block answers not supported by the context."""
import re

from app.services.ai.retrieval import STOPWORDS, key_for

_WORD = re.compile(r"[a-z]+")
_NUMBER = re.compile(r"\d+")

# Words an answer may use that need not appear in the source text.
_FILLER = STOPWORDS | {
    "according", "official", "information", "document", "documents", "listing",
    "states", "stated", "says", "said", "mentioned", "mention", "provided", "page",
    "given", "yes", "also", "per", "following", "stating", "details", "detail",
    "available", "found", "specified", "specify", "indicates", "indicate",
}


def validate_answer(answer: str, context: str, min_support: float = 0.7) -> tuple[bool, str]:
    """Check that an answer only uses words and numbers found in ``context``.

    * every number in the answer (times, dates, counts) must appear in the context
    * at least ``min_support`` of its meaningful words must appear in the context
    """
    context_lower = context.lower()
    context_numbers = set(_NUMBER.findall(context_lower))
    answer_numbers = set(_NUMBER.findall(answer.lower()))
    unsupported_numbers = answer_numbers - context_numbers
    if unsupported_numbers:
        return False, f"numbers not in sources: {sorted(unsupported_numbers)}"

    context_keys = {key_for(w) for w in _WORD.findall(context_lower)}
    words = [w for w in _WORD.findall(answer.lower()) if w not in _FILLER and len(w) > 2]
    if not words:
        return False, "empty answer"
    supported = sum(1 for w in words if key_for(w) in context_keys)
    ratio = supported / len(words)
    if ratio < min_support:
        return False, f"only {ratio:.0%} of the answer is supported by sources"
    return True, "ok"
