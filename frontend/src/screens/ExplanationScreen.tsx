import { ArrowLeft, ListChecks, CalendarDays, CircleHelp, Wallet } from "lucide-react";
import { useEffect } from "react";

import { LetterFacts } from "@/components/LetterFacts";
import { Num } from "@/components/Num";
import { ScamStatus } from "@/components/ScamStatus";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { t, type Lang, type StringKey } from "@/i18n";
import type { Proposal } from "@/lib/api";
import { formatDate } from "@/lib/dates";
import { formatCents } from "@/lib/format";
import type { Screen, ScreenProps } from "@/lib/screens";

/** The plain-words explanation, the scam check result, and ONE action. */
export function ExplanationScreen({ lang, go, letter }: ScreenProps) {
  useEffect(() => {
    if (!letter) go("capture");
  }, [letter, go]);
  if (!letter) return null;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl leading-snug font-bold">{t(lang, "explanation_title")}</h1>

      <Card>
        {/* The explanation is written in the letter's chosen language. */}
        <p lang={letter.language} className="text-lg leading-relaxed whitespace-pre-line">
          {letter.explanation}
        </p>
        <LetterFacts lang={lang} letter={letter} />
      </Card>

      <ScamStatus lang={lang} scam={letter.scam} />

      <ActionCard lang={lang} proposal={letter.proposal} go={go} />

      <Button variant="outline" onClick={() => go("audit")}>
        <ListChecks aria-hidden="true" />
        {t(lang, "audit_log")}
      </Button>
      <Button variant="outline" onClick={() => go("capture")}>
        <ArrowLeft className="rtl:rotate-180" aria-hidden="true" />
        {t(lang, "start_over")}
      </Button>
    </div>
  );
}

/** Why payment is not offered, in plain words. Unknown reasons get a general line. */
function blockMessage(reason: string | null): StringKey {
  if (reason === "unknown_payee") return "cannot_pay_unknown_payee";
  if (reason === "readings_disagree") return "cannot_pay_readings_disagree";
  if (reason === "already_paid") return "already_paid";
  return "cannot_pay_generic";
}

function ActionCard({
  lang,
  proposal,
  go,
}: {
  lang: Lang;
  proposal: Proposal;
  go: (screen: Screen) => void;
}) {
  if (proposal.action === "pay" && proposal.amount_cents !== null && proposal.payee_name) {
    const amount = formatCents(proposal.amount_cents);
    return (
      <Card className="border-2 border-primary">
        <CardTitle className="flex items-center gap-2">
          <Wallet className="size-6 shrink-0" aria-hidden="true" />
          {t(lang, "action_pay_title")}
        </CardTitle>
        <p>
          {t(lang, "pay_to")}: <bdi className="font-bold">{proposal.payee_name}</bdi>
          {proposal.due_date && (
            <>
              <br />
              {t(lang, "due_date")}: <Num>{formatDate(proposal.due_date, lang)}</Num>
            </>
          )}
        </p>
        {/* Opens the confirm dialog. Nothing is paid until the user says yes there. */}
        <Button size="lg" onClick={() => go("confirm")}>
          {t(lang, "pay_button", { amount })}
        </Button>
      </Card>
    );
  }

  if (proposal.action === "calendar" && proposal.due_date) {
    return (
      <Card>
        <CardTitle className="flex items-center gap-2">
          <CalendarDays className="size-6 shrink-0" aria-hidden="true" />
          {t(lang, "action_calendar_title")}
        </CardTitle>
        <p className="text-2xl font-bold">
          <Num>{formatDate(proposal.due_date, lang)}</Num>
        </p>
        <p className="text-muted-foreground">{t(lang, blockMessage(proposal.block_reason))}</p>
      </Card>
    );
  }

  if (proposal.block_reason === "proposal_rejected") {
    // The user just said "No, don't pay".
    return (
      <Card>
        <CardTitle className="flex items-center gap-2">
          <CircleHelp className="size-6 shrink-0" aria-hidden="true" />
          {t(lang, "nothing_paid")}
        </CardTitle>
      </Card>
    );
  }

  return (
    <Card>
      <CardTitle className="flex items-center gap-2">
        <CircleHelp className="size-6 shrink-0" aria-hidden="true" />
        {t(lang, "action_ask_title")}
      </CardTitle>
      {proposal.block_reason && proposal.block_reason !== "not_a_bill" && (
        <p className="text-muted-foreground">{t(lang, blockMessage(proposal.block_reason))}</p>
      )}
    </Card>
  );
}
