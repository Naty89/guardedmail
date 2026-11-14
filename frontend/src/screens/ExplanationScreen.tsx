import { ArrowLeft, CalendarDays, CircleHelp, ListChecks, Wallet } from "lucide-react";
import { useEffect } from "react";

import { AskBox } from "@/components/AskBox";
import { LetterFacts } from "@/components/LetterFacts";
import { Num } from "@/components/Num";
import { PlayButton } from "@/components/PlayButton";
import { ScamStatus } from "@/components/ScamStatus";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { t, type Lang, type StringKey } from "@/i18n";
import { letterAudioUrl, type Proposal } from "@/lib/api";
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
    <div className="flex flex-col gap-5">
      <h1 className="text-[1.75rem] leading-tight">{t(lang, "explanation_title")}</h1>

      <Card className="gap-5">
        {/* The explanation is written in the letter's chosen language. */}
        <p lang={letter.language} className="m-0 text-lg leading-relaxed whitespace-pre-line">
          {letter.explanation}
        </p>
        <PlayButton
          lang={lang}
          audioUrl={letterAudioUrl(letter.letter_id)}
          language={letter.language}
          text={letter.explanation}
        />
        <LetterFacts lang={lang} letter={letter} />
      </Card>

      <ScamStatus lang={lang} scam={letter.scam} />

      <ActionCard lang={lang} proposal={letter.proposal} go={go} />

      <AskBox lang={lang} letter={letter} />

      <nav className="flex flex-wrap justify-center gap-x-4 border-t border-hairline pt-4">
        <Button variant="ghost" className="px-2" onClick={() => go("audit")}>
          <ListChecks aria-hidden="true" />
          {t(lang, "audit_log")}
        </Button>
        <Button variant="ghost" className="px-2" onClick={() => go("capture")}>
          <ArrowLeft className="rtl:rotate-180" aria-hidden="true" />
          {t(lang, "start_over")}
        </Button>
      </nav>
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
      <section className="on-dark relative flex flex-col gap-4 overflow-hidden rounded-2xl bg-primary p-5 text-white shadow-card">
        <span aria-hidden="true" className="pointer-events-none absolute -end-8 -top-8 size-24 rounded-full bg-accent" />
        <CardTitle className="relative flex items-center gap-2.5 pe-14">
          <Wallet className="size-6 shrink-0 text-accent" aria-hidden="true" />
          {t(lang, "action_pay_title")}
        </CardTitle>
        <p className="m-0 text-on-primary-muted">
          {t(lang, "pay_to")}: <bdi className="font-semibold text-white">{proposal.payee_name}</bdi>
          {proposal.due_date && (
            <>
              <br />
              {t(lang, "due_date")}: <Num dir="auto">{formatDate(proposal.due_date, lang)}</Num>
            </>
          )}
        </p>
        {/* Opens the confirm dialog. Nothing is paid until the user says yes there. */}
        <Button size="lg" variant="accent" onClick={() => go("confirm")}>
          {t(lang, "pay_button", { amount })}
        </Button>
      </section>
    );
  }

  if (proposal.action === "calendar" && proposal.due_date) {
    return (
      <Card>
        <CardTitle className="flex items-center gap-2.5">
          <CalendarDays className="size-6 shrink-0 text-primary" aria-hidden="true" />
          {t(lang, "action_calendar_title")}
        </CardTitle>
        <p className="m-0 font-heading text-2xl font-semibold">
          <Num dir="auto">{formatDate(proposal.due_date, lang)}</Num>
        </p>
        <p className="m-0 text-muted-foreground">{t(lang, blockMessage(proposal.block_reason))}</p>
      </Card>
    );
  }

  if (proposal.block_reason === "proposal_rejected") {
    // The user just said "No, don't pay".
    return (
      <Card>
        <CardTitle className="flex items-center gap-2.5">
          <CircleHelp className="size-6 shrink-0 text-primary" aria-hidden="true" />
          {t(lang, "nothing_paid")}
        </CardTitle>
      </Card>
    );
  }

  return (
    <Card>
      <CardTitle className="flex items-center gap-2.5">
        <CircleHelp className="size-6 shrink-0 text-primary" aria-hidden="true" />
        {t(lang, "action_ask_title")}
      </CardTitle>
      {proposal.block_reason && proposal.block_reason !== "not_a_bill" && (
        <p className="m-0 text-muted-foreground">{t(lang, blockMessage(proposal.block_reason))}</p>
      )}
    </Card>
  );
}
