"""Step 3 - retrieval: find which official chunks relate to the question.

This is deliberately simple keyword matching with a small synonym table, so
it works offline and is easy to explain. A question is only treated as
answerable when most of its meaningful words are covered by official text.
"""
import re
from dataclasses import dataclass, field

from app.services.ai.processing import Chunk

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "am", "do", "does",
    "did", "will", "would", "can", "could", "should", "shall", "may", "might", "i",
    "me", "my", "we", "us", "our", "you", "your", "it", "its", "this", "that",
    "these", "those", "of", "for", "in", "on", "at", "to", "from", "by", "with",
    "and", "or", "but", "not", "no", "so", "if", "as", "there", "any", "have",
    "has", "had", "what", "which", "how", "many", "much", "please", "tell", "about",
    "get", "give", "know", "let", "also", "just", "than", "then", "them", "they",
    "who", "whom", "whose", "event", "events", "college", "collegehub", "hub", "happening", "going",
    "whats", "s", "t", "ll", "re", "ve",
}

# Words that mean roughly the same thing share one group name.
GROUPS = {
    "TIME": "when time start starts started begin begins begin commence commences "
            "kickoff timing date day dates times starting beginning",
    "PLACE": "where venue location hall room place address auditorium building campus",
    "END": "end ends ending finish finishes conclude concludes over",
    "AGENDA": "agenda schedule program programme itinerary session sessions timeline "
              "plan speakers talks",
    "REG": "register registration registrations registered enrol enroll enrolment "
           "signup apply application deadline last closing close",
    "FEE": "fee fees cost costs price prices paid pay payment amount fare",
    "CAPACITY": "capacity seats seat limit slots slot spots spot available availability",
    "ORGANIZER": "organiser organizer organisers organizers organising organizing "
                 "coordinator coordinators convener contact",
    "SPEAKER": "speaker speakers keynote presenter presenters",
    "JUDGE": "judge judges jury panel",
    "CONTACT": "email phone number reach helpdesk help",
    "CERT": "certificate certificates certification",
    "DRESS": "dress attire uniform wear code",
    "FOOD": "food lunch dinner snacks snack refreshment refreshments tea coffee meal "
            "meals breakfast break",
    "PRIZE": "prize prizes reward rewards award awards winner winners cash",
    "RULES": "rule rules guideline guidelines policy policies regulation regulations",
    "TEAM": "team teams group groups solo individual member members size",
    "BRING": "bring carry laptop laptops need needed require required requirement "
             "requirements prerequisite prerequisites",
    "ELIGIBLE": "eligible eligibility open allowed department year semester branch",
    "CATEGORY": "category type kind",
    "TOPIC": "topic topics about cover covers covered learn theme",
}

_WORD_TO_GROUP = {w: name for name, words in GROUPS.items() for w in words.split()}
_TOKEN = re.compile(r"[a-z0-9]+")


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def key_for(word: str) -> str:
    """Normalise a word to a synonym-group name or its stem."""
    if word in _WORD_TO_GROUP:
        return _WORD_TO_GROUP[word]
    stem = _stem(word)
    return _WORD_TO_GROUP.get(stem, stem)


def keys_in(text: str) -> set[str]:
    return {key_for(w) for w in _TOKEN.findall(text.lower()) if w not in STOPWORDS}


def raw_stems(text: str) -> set[str]:
    """Literal word stems (no synonym grouping), used to break ties."""
    return {_stem(w) for w in _TOKEN.findall(text.lower()) if w not in STOPWORDS}


def question_keys(question: str) -> dict[str, str]:
    """Map each meaningful key to the first word the user typed for it."""
    keys: dict[str, str] = {}
    for word in _TOKEN.findall(question.lower()):
        if word in STOPWORDS or len(word) < 2:
            continue
        keys.setdefault(key_for(word), word)
    return keys


@dataclass
class Retrieval:
    keys: dict[str, str]
    ranked: list = field(default_factory=list)   # [(Chunk, matched_keys)]
    covered: set = field(default_factory=set)

    @property
    def coverage(self) -> float:
        return len(self.covered) / len(self.keys) if self.keys else 0.0

    @property
    def missing_words(self) -> list[str]:
        return [word for key, word in self.keys.items() if key not in self.covered]

    @property
    def found(self) -> bool:
        return bool(self.ranked) and self.coverage >= 0.6


def retrieve(question: str, chunks: list[Chunk], top_k: int = 6) -> Retrieval:
    keys = question_keys(question)
    result = Retrieval(keys=keys)
    if not keys:
        return result

    scored = []
    for index, chunk in enumerate(chunks):
        matched = set(keys) & keys_in(chunk.text)
        if matched:
            scored.append((len(matched), -len(chunk.text), -index, chunk, matched))
    scored.sort(key=lambda row: row[:3], reverse=True)

    for _count, _length, _index, chunk, matched in scored[:top_k]:
        result.ranked.append((chunk, matched))
        result.covered |= matched
    return result
