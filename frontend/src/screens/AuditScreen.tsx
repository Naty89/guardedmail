import {
  ArrowLeft,
  Ban,
  CircleCheck,
  CircleX,
  FileSearch,
  Loader,
  MessageCircleQuestion,
  ShieldAlert,
  ShieldCheck,
  ThumbsDown,
  ThumbsUp,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";

import { Num } from "@/components/Num";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { t, type Lang } from "@/i18n";
import { getAudit, type AuditEvent, type AuditLog } from "@/lib/api";
import { formatCents } from "@/lib/format";
import type { ScreenProps } from "@/lib/screens";

/** Plain-words line and icon for each kind of event. */
function describe(event: AuditEvent, lang: Lang): { icon: LucideIcon; text: string } {
  const data = event.data;
  switch (event.event) {
    case "letter_read":
      return { icon: FileSearch, text: t(lang, "ev_letter_read") };
    case "read_failed":
      return { icon: CircleX, text: t(lang, "ev_read_failed") };
    case "scam_checked":
      return { icon: ShieldAlert, text: t(lang, "ev_scam_checked") };
    case "policy_decided":
      return data.allowed === true
        ? { icon: ShieldCheck, text: t(lang, "ev_policy_allowed") }
        : { icon: Ban, text: t(lang, "ev_policy_blocked") };
    case "confirm_requested":
      return { icon: ThumbsUp, text: t(lang, "ev_confirm_requested") };
    case "proposal_rejected":
      return { icon: ThumbsDown, text: t(lang, "ev_proposal_rejected") };
    case "payment_executed":
      return {
        icon: Wallet,
        text: t(lang, "ev_payment_executed", {
          amount: formatCents(Number(data.amount_cents ?? 0)),
        }),
      };
    case "question_asked":
      return { icon: MessageCircleQuestion, text: t(lang, "ev_question_asked") };
    case "payment_blocked":
      return { icon: Ban, text: t(lang, "ev_payment_blocked") };
    default:
      return { icon: CircleCheck, text: event.event };
  }
}

function clock(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/** What the app did for this letter, oldest first, read from the audit log. */
export function AuditScreen({ lang, go, letter, receipt }: ScreenProps) {
  const [log, setLog] = useState<AuditLog | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getAudit(letter?.letter_id)
      .then((result) => !cancelled && setLog(result))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [letter?.letter_id]);

  function back() {
    if (!letter) go("capture");
    else if (receipt) go("receipt");
    else go(letter.proposal.action === "flag" ? "scam_blocked" : "explanation");
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-[1.75rem] leading-tight">{t(lang, "audit_log")}</h1>
        <p className="mt-1 text-muted-foreground">{t(lang, "audit_intro")}</p>
      </div>

      <div role="status" aria-live="polite">
        {!log && !failed && (
          <p className="flex items-center gap-2 font-semibold">
            <Loader className="size-5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            {t(lang, "checking_connection")}
          </p>
        )}
        {failed && <p className="font-semibold text-danger">{t(lang, "reading_error")}</p>}
        {log &&
          (log.chain_ok ? (
            <p className="flex items-center gap-2 font-semibold text-ok">
              <CircleCheck className="size-6 shrink-0" aria-hidden="true" />
              {t(lang, "log_intact")}
            </p>
          ) : (
            <p className="flex items-start gap-2 rounded-xl bg-danger-soft p-3 font-semibold text-danger">
              <CircleX className="mt-0.5 size-6 shrink-0" aria-hidden="true" />
              {t(lang, "log_broken")}
            </p>
          ))}
      </div>

      {log && (
        <Card className="px-5 pt-6 pb-2">
          {log.events.length === 0 ? (
            <p className="m-0 pb-4 text-muted-foreground">{t(lang, "log_empty")}</p>
          ) : (
            <ol className="m-0 flex list-none flex-col p-0">
              {log.events.map((event) => {
                const { icon: Icon, text } = describe(event, lang);
                return (
                  <li
                    key={event.hash}
                    className="relative flex items-start gap-4 pb-6 before:absolute before:start-[1.0625rem] before:top-10 before:bottom-1 before:w-px before:bg-hairline last:before:hidden"
                  >
                    <span className="relative z-10 flex size-9 shrink-0 items-center justify-center rounded-full bg-primary-soft text-primary">
                      <Icon className="size-[1.1rem]" aria-hidden="true" />
                    </span>
                    <div className="pt-0.5">
                      <p className="m-0 leading-snug font-semibold">{text}</p>
                      <p className="m-0 text-sm text-muted-foreground">
                        <Num>{clock(event.ts)}</Num>
                      </p>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </Card>
      )}

      <Button variant="ghost" onClick={back}>
        <ArrowLeft className="rtl:rotate-180" aria-hidden="true" />
        {t(lang, "back")}
      </Button>
    </div>
  );
}
