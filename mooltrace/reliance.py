"""Reliance of a citation sentence. Fixed questions, then a fixed weight.

The class describes how the citing text uses the flagged study. It does not
say the study is right or wrong, and it does not score Semantic Scholar's
own intent labels.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

# Counted toward warn/block and the independent-source count.
WEIGHT_FLOOR = 0.5
# Retired. A multiplied path-strength floor hid counted EoC/retraction
# chains (Allen 2013 mention 0.55 × uses 0.85 = 0.4675). Hop WEIGHT_FLOOR
# is the counted gate. Path strength is still the product of weights.
STRENGTH_FLOOR = 0.5
PATH_SCORE_FLOOR = 0.25
PATH_RULE = (
    "algo.SPpaths decides: strongest path per flagged Work; counted if "
    "every hop is evidenced and each hop weight is ≥ 0.5; counted + "
    "retraction → block; counted + EoC → warn; flagged with an "
    "unverified hop → warn (can't verify); a hop below 0.5 → pass "
    "(cites a flagged study only in passing). A multiplied path-strength "
    "floor is not applied. Zero SPpaths rows is a pass; PATHS_TO_NOTICE "
    "is not a second verdict. Python PATH_RULE is not a verdict. If the "
    "algorithm errors, exit 3."
)
STRONG_RELIANCE = frozenset({"included", "relies", "uses_data_or_method"})
# Unjudged RESTS_ON hops. Higher than -ln(0.2) so a judged background hop
# still ranks ahead of a missing judgment.
UNJUDGED_COST = 20.0


def hop_cost(weight: float | None) -> float:
    """Edge cost for algo.SPpaths: -ln(weight). Stronger reliance is cheaper."""
    try:
        value = float(weight) if weight is not None else 0.0
    except (TypeError, ValueError):
        value = 0.0
    if value <= 0:
        return UNJUDGED_COST
    return max(1e-9, -math.log(value))

# The draft or cited web page cannot hedge-bypass a publisher notice.
# Scholarly full text can still set a study aside.
_NO_DISPUTE_SOURCES = frozenset({"draft", "page", "page_list"})

WEIGHTS = {
    "included": 1.0,
    "relies": 1.0,
    "uses_data_or_method": 0.85,
    "mention": 0.55,
    "background": 0.2,
    "critical": 0.0,
    "unresolved": 0.0,
}

_STOP = frozenset(
    """
    a an the of and or in on for with without to from by at as is are was were
    be this that these those study trial paper review people type
    """.split()
)

# The citer used the study's numbers or procedure.
_USES = (
    "analysing the results",
    "analyzing the results",
    "analysed the results",
    "analyzed the results",
    "reanalysed",
    "reanalyzed",
    "data from",
    "we analysed",
    "we analyzed",
    "were pooled",
    "was pooled",
    "pooled",
    "extracted data",
    "data were extracted",
    "we included",
    "was included",
    "were included",
    "included in the",
    "included this",
    "included the",
)

# The citer states the study's result as support.
# Weak phrases show up in nearby sentences that are not about this study,
# so they count only when the author or the DOI is in the sentence.
_RELIES_STRONG = (
    "found",
    "showed",
    "shown",
    "reported",
    "demonstrated",
    "reduced",
    "lowered",
    "decreased",
)
_RELIES_WEAK = (
    "improved",
    "increased",
    "significant",
    "was associated",
    "were associated",
    "effect size",
    "fasting",
)

# The citer disputes or sets aside the study. These outrank a use.
_REJECT = (
    "expression of concern",
    "do not support",
    "does not support",
    "did not support",
    "failed to replicate",
    "could not replicate",
    "contradict",
    "contradicted",
    "contradicts",
    "contradiction",
    "disput",
    "dispute",
    "disputed",
    "disputes",
    "unreliable",
    "questionable",
    "excluded this",
    "excluded the",
    "we excluded",
    "was excluded",
    "were excluded",
    "concerns about",
)


def _has(sentence: str, phrase: str) -> bool:
    return (
        re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", sentence.lower())
        is not None
    )


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(token) > 2 and token not in _STOP
    }


def doi_markers(doi: str) -> list[str]:
    """Substrings that mean this DOI, including a journal locator."""
    raw = (doi or "").strip().lower()
    if not raw:
        return []
    marks = [raw]
    tail = raw.split("/", 1)[-1]
    marks.append(tail)
    if "." in tail:
        marks.append(tail.replace(".", "/"))
        bits = tail.split(".")
        if len(bits) >= 3:
            loc = ".".join(bits[-3:])
            marks.append(loc)
            marks.append(loc.replace(".", "/"))
    out: list[str] = []
    for mark in marks:
        if len(mark) >= 8 and mark not in out:
            out.append(mark)
    return out


def citation_group_size(sentence: str) -> int:
    """How many references sit in the largest citation cluster.

    A cluster is a bracketed list such as ``(6-9, 12, 13)`` or an unbracketed
    run of at least three reference numbers. A year is four digits and is not
    a reference number.
    """
    best = 1

    def absorb(chunk: str) -> int:
        found: set[int] = set()
        for part in re.split(r"[,;]", chunk):
            part = part.strip()
            span = re.fullmatch(r"(\d{1,3})\s*[-–—]\s*(\d{1,3})", part)
            if span:
                start, end = int(span.group(1)), int(span.group(2))
                if 1 <= start <= end <= 250 and end - start < 40:
                    found.update(range(start, end + 1))
                continue
            single = re.fullmatch(r"\d{1,3}", part)
            if single:
                number = int(single.group(0))
                if 1 <= number <= 250:
                    found.add(number)
        return len(found)

    for match in re.finditer(r"[\[\(]([^\]\)]{1,80})[\]\)]", sentence):
        best = max(best, absorb(match.group(1)))
    cluster = re.compile(
        r"\b\d{1,3}(?:\s*[-–—]\s*\d{1,3})?(?:\s*,\s*\d{1,3}(?:\s*[-–—]\s*\d{1,3})?){2,}\b"
    )
    for match in cluster.finditer(sentence):
        best = max(best, absorb(match.group(0)))
    return best


def cites_a_different_year(sentence: str, author: str | None, year: str | int | None) -> bool:
    """Yes when the surname is tied to a different year than the cited study."""
    if not author or year in (None, ""):
        return False
    try:
        wanted = str(int(year))
    except (TypeError, ValueError):
        wanted = str(year)
    pattern = (
        rf"\b{re.escape(author)}\b.{{0,20}}((?:19|20)\d{{2}})"
        rf"|((?:19|20)\d{{2}}).{{0,16}}\b{re.escape(author)}\b"
    )
    found = [item for pair in re.findall(pattern, sentence, re.I) for item in pair if item]
    return bool(found) and wanted not in found


def names_the_author(sentence: str, author: str | None) -> bool:
    family = (author or "").strip()
    if len(family) < 3:
        return False
    return re.search(rf"\b{re.escape(family)}\b", sentence, re.I) is not None


def mentions_doi(sentence: str, doi: str | None) -> bool:
    lowered = sentence.lower()
    return any(marker in lowered for marker in doi_markers(doi or ""))


def title_overlap(sentence: str, title: str | None) -> float:
    title_tokens = _tokens(title or "")
    if not title_tokens:
        return 0.0
    return len(title_tokens & _tokens(sentence)) / len(title_tokens)


def is_background_list(sentence: str) -> bool:
    """Yes when this sentence is one of three or more references in a cluster."""
    return citation_group_size(sentence) >= 3


def is_bibliography_line(sentence: str, title: str | None) -> bool:
    """Yes when the sentence is the reference-list entry, not a discussion of it."""
    if title_overlap(sentence, title) < 0.72:
        return False
    has_year = re.search(r"\b(?:19|20)\d{2}\b", sentence) is not None
    reference_shape = has_year and (
        "et al" in sentence.lower()
        or sentence.count(",") >= 3
        or re.search(r"\b\d+\s*\(\d+\)\s*:\s*\d+", sentence) is not None
    )
    almost_only_the_title = len(sentence) < len(title or "") + 40
    return reference_shape or almost_only_the_title


def is_author_list(sentence: str) -> bool:
    """Yes when the line is a run of bibliographic names, not a discussion."""
    return len(re.findall(r"[A-Z]\.[A-Z]\.", sentence)) >= 3


def is_reference_metadata(sentence: str) -> bool:
    """Yes when the line is a bibliography stub: doi, PMC, PubMed, Scholar."""
    lowered = sentence.lower()
    if "pmc free article" in lowered or "google scholar" in lowered:
        return True
    return (
        re.search(r"\bdoi:\s*10\.\d{4,9}/", lowered) is not None
        and ("[doi" in lowered or "pubmed" in lowered)
    )


def is_flattened_table_header(sentence: str) -> bool:
    """Yes when HTML flattened a risk-of-bias or study table into one line."""
    lowered = (sentence or "").lower()
    marks = (
        "overall bias",
        "randomization process",
        "deviations from intended",
        "bias in measurement of outcome",
        "bias to missing outcome data",
        "selecting the reported results",
        "authors randomization",
    )
    if sum(1 for mark in marks if mark in lowered) >= 2:
        return True
    return "overall bias" in lowered and "et al" in lowered and lowered.count(".") <= 1


def is_included_listing(sentence: str) -> bool:
    """Yes when the stored quote is the included-studies listing, not prose."""
    return re.match(r"listed among included studies\b", (sentence or "").strip(), re.I) is not None


def disputes_the_study(sentence: str) -> bool:
    """Yes when the citer sets the study aside or contradicts it."""
    return any(_has(sentence, phrase) for phrase in _REJECT)


def uses_data_or_method(sentence: str) -> bool:
    """Yes when the citer pools, extracts, or analyses this study's data."""
    return any(_has(sentence, phrase) for phrase in _USES)


def relies_on_the_finding(sentence: str, *, named: bool = False, has_doi: bool = False) -> bool:
    """Yes when the citer states the study's result."""
    if any(_has(sentence, phrase) for phrase in _RELIES_STRONG):
        return True
    if named or has_doi:
        return any(_has(sentence, phrase) for phrase in _RELIES_WEAK)
    return False


def classify_sentence(
    sentence: str,
    *,
    cited_doi: str | None = None,
    cited_author: str | None = None,
    cited_title: str | None = None,
    allow_dispute: bool = True,
) -> tuple[str, float]:
    """Map one citation sentence to a class and a weight.

    Questions, in order: is it only the bibliography line; does it dispute
    the study; does it use the data or method; does it rely on the finding;
    is it one of three or more references; otherwise is it a direct mention.
    A grouped citation with no author and no DOI stays background, so a
    shared reference list does not count as reliance.
    Drafts and cited web pages pass allow_dispute=False so naming an
    Expression of Concern cannot turn a counted citation into a pass.
    """
    text = re.sub(r"\s+", " ", (sentence or "")).strip()
    if not text:
        return "unresolved", WEIGHTS["unresolved"]
    if is_included_listing(text):
        return "included", WEIGHTS["included"]
    named = names_the_author(text, cited_author)
    has_doi = mentions_doi(text, cited_doi)
    group = citation_group_size(text)
    if is_bibliography_line(text, cited_title) or is_reference_metadata(text) or (
        is_author_list(text) and not uses_data_or_method(text)
    ):
        kind = "background"
    elif (
        allow_dispute
        and disputes_the_study(text)
        and (named or has_doi or _points_at_this(text))
    ):
        kind = "critical"
    elif uses_data_or_method(text) and (named or has_doi):
        kind = "uses_data_or_method"
    elif relies_on_the_finding(text, named=named, has_doi=has_doi) and (
        named or has_doi or group < 3
    ):
        kind = "relies"
    elif group >= 3:
        kind = "background"
    elif named or has_doi:
        kind = "mention"
    else:
        kind = "background"
    return kind, WEIGHTS[kind]


def _points_at_this(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(
        phrase in lowered for phrase in ("this study", "this trial", "this paper")
    )


@dataclass(frozen=True)
class Reliance:
    reliance: str
    weight: float
    sentence: str
    evidence_from: str


def included_evidence(where: str, source_url: str) -> Reliance:
    """Audit quote for a trial listed among a review's included studies."""
    place = re.sub(r"\s+", " ", (where or "").strip()).rstrip(".")
    sentence = f"Listed among included studies ({place})" if place else "Listed among included studies"
    return Reliance("included", WEIGHTS["included"], sentence, source_url)


def prefer_included(picked: Reliance | None, included: Reliance | None) -> Reliance | None:
    """An included-studies listing outranks a mention. A scholarly exclusion stands."""
    if included is None:
        return picked
    if picked is not None and picked.reliance == "critical":
        return picked
    return included


def _focus_quote(sentence: str, author: str | None, doi: str | None, year: str = "") -> str:
    """Verbatim slice. Long blocks keep the words around the author and year."""
    if len(sentence) <= 420:
        return sentence
    match = None
    if author and len(author) >= 3 and year:
        match = re.search(
            rf"\b{re.escape(author)}\b(?:\W|\w){{0,24}}{re.escape(year)}|{re.escape(year)}(?:\W|\w){{0,24}}\b{re.escape(author)}\b",
            sentence,
            re.I,
        )
    if match is None and author and len(author) >= 3:
        match = re.search(rf"\b{re.escape(author)}\b", sentence, re.I)
    if match is None:
        lowered = sentence.lower()
        for marker in doi_markers(doi or ""):
            at = lowered.find(marker)
            if at >= 0:
                match_start = at
                break
        else:
            match_start = 0
    else:
        match_start = match.start()
    start = max(0, match_start - 140)
    end = min(len(sentence), match_start + 280)
    if start > 0:
        gap = sentence.find(" ", start)
        if 0 <= gap < start + 24:
            start = gap + 1
    if end < len(sentence):
        gap = sentence.rfind(" ", match_start, end)
        if gap > match_start:
            end = gap
    return sentence[start:end].strip()


def as_source_list(item: Reliance) -> Reliance:
    """A source-list hit cites the work. It is not a prose claim about results.

    Consumer pages cite through a source list. That is a counted mention,
    not background, or the page → study hop would never warn.
    """
    if item.reliance in {"included", "relies", "uses_data_or_method"}:
        return Reliance("mention", WEIGHTS["mention"], item.sentence, item.evidence_from)
    return item


def choose_reliance(
    candidates: list[tuple[str, str]],
    *,
    cited_doi: str | None = None,
    cited_author: str | None = None,
    cited_title: str | None = None,
    cited_year: str | int | None = None,
) -> Reliance | None:
    """Pick the candidate sentence with the highest weight.

    ``candidates`` are ``(sentence, evidence_from)`` pairs. The stored
    sentence is the text that decided the class, whitespace collapsed and
    cut at 800 characters so the edge stays an audit quote.
    """
    best: Reliance | None = None
    best_key: tuple[float, int, int, int, int] | None = None
    year = ""
    if cited_year not in (None, ""):
        try:
            year = str(int(cited_year))
        except (TypeError, ValueError):
            year = str(cited_year)
    source_rank = {
        "pmc_full_text": 4,
        "europepmc_xml": 4,
        "pmc_html": 4,
        "pmc_oa": 4,
        "pmc_included": 5,
        "publisher_html": 3,
        "publisher_pdf": 3,
        "page": 3,
        "draft": 3,
        "semantic_scholar": 2,
        "openalex_abstract": 1,
        "europepmc_references": 0,
    }
    class_rank = {"included": 3, "relies": 2, "uses_data_or_method": 1}
    for sentence, source in candidates:
        text = re.sub(r"\s+", " ", sentence or "").strip()
        if len(text) < 12:
            continue
        if is_flattened_table_header(text) and not is_included_listing(text):
            continue
        if cites_a_different_year(text, cited_author, year):
            continue
        kind, weight = classify_sentence(
            text,
            cited_doi=cited_doi,
            cited_author=cited_author,
            cited_title=cited_title,
            allow_dispute=source not in _NO_DISPUTE_SOURCES,
        )
        named = names_the_author(text, cited_author)
        has_doi = mentions_doi(text, cited_doi)
        overlap = title_overlap(text, cited_title)
        if source in _NO_DISPUTE_SOURCES:
            if source == "page_list" and kind in {"included", "relies", "uses_data_or_method"}:
                kind, weight = "mention", WEIGHTS["mention"]
            elif kind == "background" and (named or has_doi or overlap >= 0.5):
                # A health page's source list is how it cites. Count it.
                kind, weight = "mention", WEIGHTS["mention"]
        quote = text if is_included_listing(text) else _focus_quote(text, cited_author, cited_doi, year)
        year_hit = 1 if year and year in quote else 0
        host_rank = source_rank.get(source, 0)
        if host_rank == 0 and (
            "pmc.ncbi.nlm.nih.gov" in (source or "").lower()
            or "europepmc.org" in (source or "").lower()
        ):
            host_rank = 4
        rank = (weight, class_rank.get(kind, 0), year_hit, -len(quote), host_rank)
        if best_key is None or rank > best_key:
            best_key = rank
            best = Reliance(kind, weight, quote, source)
    return best
