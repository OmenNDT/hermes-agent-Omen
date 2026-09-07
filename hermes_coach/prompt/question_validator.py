from __future__ import annotations

import re
import unicodedata
from enum import StrEnum

from hermes_coach.domain.models import ImmutableModel


_ADVICE_PATTERN = re.compile(
    r"\b(ban nen|ban can|ban phai|toi khuyen|toi de nghi|toi de xuat|"
    r"theo toi|toi nghi ban|co nghi nen|tai sao ban khong|"
    r"ban co the thu|mot lua chon la|se tot hon neu|"
    r"lua chon tot nhat|tot nhat la)\b"
)
_INTERROGATIVE_PATTERN = re.compile(
    r"\b(dieu gi|cai gi|khi nao|bao gio|o dau|tai sao|vi sao|"
    r"nhu the nao|the nao|bao nhieu|gi|ai|what|when|where|who|why|how)\b"
)
_COMPOUND_CLAUSE_PATTERN = re.compile(
    r"\b(va|roi|sau do)\s+(ban|minh|toi|anh|chi|em)\s+"
    r"(se|muon|can|co the|lam|chon)\b"
)
_REFLECTION_PREFIX_PATTERN = re.compile(
    r"^(ban vua (noi|nhac|chia se)|ban da (noi|nhac|chia se)|"
    r"minh nghe thay|toi nghe thay|theo loi ban)\b"
)
_QUOTE_PATTERN = re.compile(r"[“\"‘']([^”\"’']+)[”\"’']")


class QuestionRejectCode(StrEnum):
    EMPTY = "empty"
    MULTIPLE_QUESTIONS = "multiple_questions"
    NOT_A_QUESTION = "not_a_question"
    STANDALONE_STATEMENT = "standalone_statement"
    IMPERATIVE = "imperative"
    DISGUISED_ADVICE = "disguised_advice"
    JUDGMENT = "judgment"
    DIAGNOSIS_OR_LABEL = "diagnosis_or_label"
    AUTHORITY_CLAIM = "authority_claim"
    LEADING_ANSWER = "leading_answer"
    MULTIPLE_FOCUSES = "multiple_focuses"
    INFERRED_CAUSE = "inferred_cause"


class QuestionValidationResult(ImmutableModel):
    valid: bool
    normalized_question: str
    reason_codes: tuple[QuestionRejectCode, ...] = ()


def validate_question(
    question: str,
    *,
    grounded_coachee_input: str | None = None,
) -> QuestionValidationResult:
    text = question.strip()
    normalized = _normalize(text)
    reasons: list[QuestionRejectCode] = []
    if not text:
        reasons.append(QuestionRejectCode.EMPTY)
    if text.count("?") > 1:
        reasons.append(QuestionRejectCode.MULTIPLE_QUESTIONS)
    elif text.count("?") != 1 or not text.endswith("?"):
        reasons.append(QuestionRejectCode.NOT_A_QUESTION)
    lead_in = _lead_in(text)
    if lead_in is not None and not _is_grounded_reflection(
        lead_in,
        grounded_coachee_input,
    ):
        reasons.append(QuestionRejectCode.STANDALONE_STATEMENT)
    if re.search(r"^(hay|hãy|hay thu|thử|thu|ban hay|ban thu)\b", normalized):
        reasons.append(QuestionRejectCode.IMPERATIVE)
    if _ADVICE_PATTERN.search(normalized):
        reasons.append(QuestionRejectCode.DISGUISED_ADVICE)
    if re.search(
        r"\b(sai|kem coi|yeu kem|thieu y chi|thieu ky luat|vo trach nhiem|that bai)\b",
        normalized,
    ):
        reasons.append(QuestionRejectCode.JUDGMENT)
    if re.search(r"\b(tu pha hoai|bat luc|tram cam|roi loan|co van de tam ly)\b", normalized):
        reasons.append(QuestionRejectCode.DIAGNOSIS_OR_LABEL)
    if re.search(r"\b(toi biet dieu tot nhat|toi hieu ban hon|phai nghe toi)\b", normalized):
        reasons.append(QuestionRejectCode.AUTHORITY_CLAIM)
    if re.search(r"\b(chang phai .* sao|ro rang .* dung khong)\b", normalized):
        reasons.append(QuestionRejectCode.LEADING_ANSWER)
    if _has_multiple_focuses(normalized, lead_in):
        reasons.append(QuestionRejectCode.MULTIPLE_FOCUSES)
    if re.search(r"\b(that bai|khong thanh cong) vi\b", normalized):
        reasons.append(QuestionRejectCode.INFERRED_CAUSE)
    unique = tuple(dict.fromkeys(reasons))
    return QuestionValidationResult(
        valid=not unique,
        normalized_question=text,
        reason_codes=unique,
    )


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize(
        "NFD", value.casefold().translate(str.maketrans("đĐ", "dD"))
    )
    no_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", no_marks).strip()


def _lead_in(question: str) -> str | None:
    match = re.match(r"^(.+)[.!;:]\s+[^?]+\?$", question)
    return match.group(1).strip() if match else None


def _is_grounded_reflection(
    lead_in: str,
    grounded_coachee_input: str | None,
) -> bool:
    if re.search(r"[.!;:]\s+", lead_in):
        return False
    normalized_lead = _normalize(lead_in)
    prefix = _REFLECTION_PREFIX_PATTERN.search(normalized_lead)
    if prefix is None:
        return False

    quotes = tuple(_normalize(match) for match in _QUOTE_PATTERN.findall(lead_in))
    if grounded_coachee_input is None:
        return False

    normalized_grounding = _normalize(grounded_coachee_input)
    if not normalized_grounding:
        return False
    if quotes:
        return all(_contains_phrase(normalized_grounding, quote) for quote in quotes)

    reflected_phrase = normalized_lead[prefix.end() :].strip()
    return _contains_phrase(normalized_grounding, reflected_phrase)


def _contains_phrase(normalized_text: str, normalized_phrase: str) -> bool:
    if not normalized_phrase:
        return False
    return f" {normalized_phrase} " in f" {normalized_text} "


def _has_multiple_focuses(normalized: str, lead_in: str | None) -> bool:
    if len(_INTERROGATIVE_PATTERN.findall(normalized)) > 1:
        return True
    if _COMPOUND_CLAUSE_PATTERN.search(normalized):
        return True
    if lead_in is None:
        return False
    normalized_lead = _normalize(lead_in)
    return bool(
        _INTERROGATIVE_PATTERN.search(normalized_lead)
        or re.search(
            r"\bban\s+(muon|chon|nghi|thay|co the|se)\b",
            normalized_lead,
        )
    )
