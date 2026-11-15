"""Calendar export: turn a letter's due date into a downloadable .ics file.

Only facts the server already holds are used:
- the due date both readings agreed on (stored in the proposal),
- the sender name (a trusted merchant name for a payable bill, otherwise the
  reader's short, pattern-checked sender text),
- the amount, but only for a payable bill (where it is policy-checked).

Letter text is untrusted, and an .ics file has its own syntax (one property per
line, so a stray newline could add a property). So every value is escaped and
stripped of control characters before it is written, and lines are folded to
the 75-byte limit in the standard.

The two reminders: 3 days before at 9:00, and on the day at 9:00.
"""

import re
from datetime import date, datetime, timezone
from uuid import UUID

from app.schemas import LANGUAGES

# language -> (word for "deadline", note, word for "amount")
TEXTS: dict[str, tuple[str, str, str]] = {
    "en": ("Deadline", "Added from Guarded Mail. Check the letter again before paying anything.", "Amount"),
    "es": ("Fecha límite", "Añadido desde Guarded Mail. Revise la carta otra vez antes de pagar.", "Monto"),
    "hi": ("अंतिम तारीख", "Guarded Mail से जोड़ा गया। कुछ भी चुकाने से पहले पत्र को फिर से देखें।", "रकम"),
    "te": ("చివరి తేదీ", "Guarded Mail నుండి జోడించబడింది. ఏదైనా చెల్లించే ముందు లేఖను మళ్లీ చూడండి.", "మొత్తం"),
    "ta": ("கடைசி தேதி", "Guarded Mail இலிருந்து சேர்க்கப்பட்டது. பணம் செலுத்தும் முன் கடிதத்தை மீண்டும் பாருங்கள்.", "தொகை"),
    "pt": ("Prazo", "Adicionado pelo Guarded Mail. Confira a carta de novo antes de pagar.", "Valor"),
    "zh": ("截止日期", "由 Guarded Mail 添加。付款前请再看一遍这封信。", "金额"),
    "ar": ("آخر موعد", "أُضيف من Guarded Mail. راجع الرسالة مرة أخرى قبل دفع أي شيء.", "المبلغ"),
    "am": ("የመጨረሻ ቀን", "ከ Guarded Mail የተጨመረ። ማንኛውንም ከመክፈልዎ በፊት ደብዳቤውን እንደገና ያረጋግጡ።", "መጠን"),
}

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f  ]")


BACKSLASH = chr(92)


def escape_text(value: str) -> str:
    """Make a value safe inside an iCalendar TEXT property."""
    value = _CONTROL.sub(" ", value)          # no stray newlines or control codes
    value = value.replace(BACKSLASH, BACKSLASH * 2)
    value = value.replace(";", BACKSLASH + ";").replace(",", BACKSLASH + ",")
    return " ".join(value.split())


def fold(line: str) -> str:
    """Wrap a long line at 75 bytes, never cutting through a multi-byte character."""
    data = line.encode("utf-8")
    if len(data) <= 75:
        return line
    parts, current, size = [], "", 0
    limit = 75
    for char in line:
        width = len(char.encode("utf-8"))
        if size + width > limit:
            parts.append(current)
            current, size, limit = "", 0, 74   # continuation lines start with a space
        current += char
        size += width
    parts.append(current)
    return "\r\n ".join(parts)


def filename_for(due: date) -> str:
    return f"guarded-mail-deadline-{due.isoformat()}.ics"


def build_ics(*, letter_id: UUID, language: str, due: date, name: str,
              amount_cents: int | None, now: datetime | None = None) -> str:
    """Return the text of an .ics file with one all-day event and two reminders.

    name          sender or merchant (escaped here)
    amount_cents  pass a value only for a payable bill; otherwise None
    """
    deadline, note, amount_word = TEXTS.get(language, TEXTS["en"])
    now = now or datetime.now(timezone.utc)
    title = f"{deadline}: {name}" if name.strip() else deadline
    description = escape_text(note)
    if amount_cents is not None:
        dollars, cents = divmod(amount_cents, 100)
        amount_line = escape_text(f"{amount_word}: ${dollars}.{cents:02d}")
        description = amount_line + BACKSLASH + "n" + description   # \n = line break in iCalendar
    next_day = date.fromordinal(due.toordinal() + 1)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Guarded Mail//Letter deadline//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{letter_id}@guarded-mail",
        f"DTSTAMP:{now.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;VALUE=DATE:{due.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{next_day.strftime('%Y%m%d')}",
        f"SUMMARY:{escape_text(title)}",
        f"DESCRIPTION:{description}",
        "TRANSP:TRANSPARENT",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{escape_text(title)}",
        "TRIGGER:-P2DT15H",     # 3 days before, at 9:00
        "END:VALARM",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{escape_text(title)}",
        "TRIGGER:PT9H",         # on the day, at 9:00
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(fold(line) for line in lines) + "\r\n"


def supported(language: str) -> bool:
    return language in LANGUAGES
