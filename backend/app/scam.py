"""Scam check: plain rules on the transcription plus the reader model's judgement.

The final risk is the STRICTER of the two. Either side alone can raise the
risk; neither can lower what the other found.

- Rules: keyword / regex matches on the transcriptions (`raw_text`).
- Model judgement: the `scam_signals` and `doc_type` that the two extraction
  passes reported. No extra model call is made here.

What leaves this module: a risk level and a list of reasons, each with a short
quote from the letter. The quotes are untrusted text for the user's screen
only. policy.py receives just the risk level.

Wording for users is "Possible scam" or "No warning signs found". A "low"
result never means a letter is safe, and it never authorises anything.
"""

import re

from app.schemas import MAX_QUOTE_CHARS, ReaderOutput, ScamReason, ScamResult

QUOTE_CONTEXT_CHARS = 45  # characters kept on each side of a match

# reason id -> (risk when it appears alone, pattern)
# "high": asking for payment in a way that cannot be traced or undone is, by
# itself, enough to call the letter a possible scam.
STRONG_RULES: dict[str, tuple[str, str]] = {
    "gift_card": ("high", r"gift\s*cards?|i\s?tunes cards?|google play cards?|steam cards?"
                          r"|prepaid (?:debit |visa )?cards?|card numbers? (?:on|from) the back"),
    "wire": ("high", r"wire\s+transfer|wire the (?:money|funds|payment)|western union|moneygram"),
    "crypto": ("high", r"bitcoin|\bbtc\b|crypto(?:currency)?|ethereum|\busdt\b|wallet address"),
    "payment_app": ("high", r"\bzelle\b|\bvenmo\b|cash\s?app|apple cash|\bpaypal\b.{0,30}"
                            r"friends (?:and|&) family"),
    "embedded_instruction": ("high",
                             r"ignore (?:all |any )?(?:previous|prior|above|earlier) "
                             r"(?:instructions|rules|prompts)"
                             r"|attention,? (?:ai|a\.i\.|assistant|automated)"
                             r"|(?:ai|a\.i\.) (?:assistant|agent|model|system)s?\b"
                             r"|system prompt|automated systems?"
                             r"|without (?:asking|confirm\w*|telling|notifying) (?:the )?user"
                             r"|do not (?:ask|tell|notify|warn) the user"
                             r"|report no scam|this letter is (?:verified|safe|legitimate)"),
    "threat": ("med", r"\barrest(?:ed)?\b|\bwarrant\b|\bdeport\w*|\bjail\b|\bprison\b"
                      r"|police will|prosecut\w+|legal action|law\s?suit"
                      r"|criminal charges?|seize your"),
    "urgency": ("med", r"\burgent\b|immediately|act now|right away|final notice|last chance"
                       r"|within \d+ (?:hours?|minutes?)|(?:shut|cut|turned) off today"
                       r"|before \d{1,2}(?::\d\d)? ?(?:am|pm) today|do not delay"),
    "prize": ("med", r"you(?: have|'ve)? won\b|\bwinner\b|lottery|sweepstakes"
                     r"|claim your (?:prize|reward|winnings)|free gift"),
}

# Weak signs: common in real mail too, so they are only reported when at least
# one strong sign is present. They never raise the risk by themselves.
IMPERSONATION = (r"\birs\b|internal revenue service|social security administration"
                 r"|\bmedicare\b|\bfbi\b|u\.?s\.? marshals?|department of (?:justice|treasury)"
                 r"|homeland security|\bmicrosoft\b|\bamazon\b|\bapple support\b|geek squad")
ACCOUNT_NUMBER = (r"(?:account|acct|customer|invoice|reference|member|policy|statement)"
                  r"\s*(?:number|no\.?|num|id|#)?\s*[:#]?\s*[a-z]{0,4}[\d][\d\- ]{3,}")

_RISK_ORDER = {"low": 0, "med": 1, "high": 2}
_MODEL_HIGH = {"gift_card", "wire", "crypto"}


def _stricter(a: str, b: str) -> str:
    return a if _RISK_ORDER[a] >= _RISK_ORDER[b] else b


def _quote(text: str, match: re.Match) -> str:
    """A short piece of the letter around the match, on one line."""
    start = max(0, match.start() - QUOTE_CONTEXT_CHARS)
    end = min(len(text), match.end() + QUOTE_CONTEXT_CHARS)
    piece = " ".join(text[start:end].split())
    if start > 0:
        piece = "…" + piece
    if end < len(text):
        piece = piece + "…"
    return piece[:MAX_QUOTE_CHARS]


def rule_signals(raw_text: str) -> tuple[str, dict[str, str]]:
    """Run the rules on one transcription. Returns (risk, {reason id: quote})."""
    found: dict[str, str] = {}
    risk = "low"
    for reason_id, (level, pattern) in STRONG_RULES.items():
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            found[reason_id] = _quote(raw_text, match)
            risk = _stricter(risk, level)
    if found:
        match = re.search(IMPERSONATION, raw_text, re.IGNORECASE)
        if match:
            found["impersonation"] = _quote(raw_text, match)
        if raw_text.strip() and not re.search(ACCOUNT_NUMBER, raw_text, re.IGNORECASE):
            found["no_account_number"] = ""
    return risk, found


def model_judgement(first: ReaderOutput, second: ReaderOutput) -> tuple[str, list[str]]:
    """Risk from what the two extraction passes reported. Returns (risk, signals)."""
    signals = list(dict.fromkeys(first.scam_signals + second.scam_signals))
    if "scam_suspect" in (first.doc_type, second.doc_type) or _MODEL_HIGH & set(signals):
        return "high", signals
    return ("med" if signals else "low"), signals


def assess(first: ReaderOutput, second: ReaderOutput) -> ScamResult:
    """Combine rules and model judgement. The stricter risk wins."""
    rule_risk, quotes = "low", {}
    for reading in (first, second):
        risk, found = rule_signals(reading.raw_text)
        rule_risk = _stricter(rule_risk, risk)
        for reason_id, quote in found.items():
            if not quotes.get(reason_id):
                quotes[reason_id] = quote
    # "no account number" only counts if NEITHER transcription shows one.
    if "no_account_number" in quotes and any(
            re.search(ACCOUNT_NUMBER, r.raw_text, re.IGNORECASE) for r in (first, second)):
        del quotes["no_account_number"]

    model_risk, model_signals = model_judgement(first, second)
    for signal in model_signals:
        quotes.setdefault(signal, "")  # the model saw it; no rule quote available

    reasons = [ScamReason(reason_id=reason_id, quote=quote)
               for reason_id, quote in quotes.items()]
    # Most telling reasons first: the ones with a quote from the letter.
    reasons.sort(key=lambda reason: reason.quote == "")
    return ScamResult(risk=_stricter(rule_risk, model_risk), reasons=reasons)
