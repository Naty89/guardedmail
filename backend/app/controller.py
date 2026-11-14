"""Controller: picks the ONE action to propose for a letter.

It receives only validated values: the policy's yes/no, the scam risk level and
whether an agreed due date exists. It never receives image pixels, the
transcription, the explanation, or the reader's payee text, so nothing written
in a letter can steer it.
"""

from app.schemas import ProposalAction, RiskLevel


def choose_action(*, pay_allowed: bool, scam_risk: RiskLevel,
                  has_due_date: bool) -> ProposalAction:
    """Return "pay", "flag", "calendar" or "ask_user".

    pay_allowed   True only when policy.decide() returned an Allow
    scam_risk     from the scam check; anything but "low" means flag
    has_due_date  both readings agreed on a real due date
    """
    if scam_risk != "low":
        return "flag"          # a possible scam is never payable
    if pay_allowed is True:
        return "pay"
    if has_due_date:
        return "calendar"      # cannot pay it, but the deadline is worth saving
    return "ask_user"
