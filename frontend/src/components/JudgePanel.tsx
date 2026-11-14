import { Bug } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { t, type Lang } from "@/i18n";
import { getAudit, getLetterDebug, type AuditLog, type Letter } from "@/lib/api";
import { SCREENS, type Screen } from "@/lib/screens";

type Debug = Record<string, unknown>;
type PayerStep = { step?: string; method?: string; path?: string; status?: number; elapsed_ms?: number; request_id?: string | null; error?: string };

/**
 * Drawer shown only with ?debug=1. Always English (judges read it).
 * Shows, for the current letter: each pipeline step with timing, the policy
 * verdict and reason IDs, the bank calls, and the hash-chained audit events.
 */
export function JudgePanel({
  lang,
  screen,
  go,
  letter,
}: {
  lang: Lang;
  screen: Screen;
  go: (screen: Screen) => void;
  letter: Letter | null;
}) {
  const [debug, setDebug] = useState<Debug | null>(null);
  const [log, setLog] = useState<AuditLog | null>(null);

  function load(open: boolean) {
    if (!open) return;
    setDebug(null);
    setLog(null);
    if (!letter) return;
    getLetterDebug(letter.letter_id).then(setDebug).catch(() => setDebug(null));
    getAudit(letter.letter_id).then(setLog).catch(() => setLog(null));
  }

  const reasons = (debug?.policy_reasons as string[] | undefined) ?? [];
  const steps = (debug?.payer_steps as PayerStep[] | undefined) ?? [];

  return (
    <Dialog onOpenChange={load}>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          lang="en"
          dir="ltr"
          className="fixed end-3 bottom-3 z-20 rounded-full shadow-md"
        >
          <Bug aria-hidden="true" />
          {t("en", "judge_panel")}
        </Button>
      </DialogTrigger>
      <DialogContent lang="en" dir="ltr" closeLabel={t("en", "close")} className="text-sm">
        <DialogTitle>{t("en", "judge_panel")}</DialogTitle>
        <DialogDescription>
          {letter ? `Letter ${letter.letter_id}` : "No letter yet. Read a letter, then open this."}
        </DialogDescription>

        {letter && debug && (
          <section className="flex flex-col gap-1">
            <h3 className="font-semibold">Pipeline</h3>
            <Row label="1. Reader (2 passes + explanation)">
              {debug.from_cache ? "from cache" : `${String(debug.reader_ms)} ms`} ·{" "}
              {(debug.model_ids as string[] | undefined)?.join(", ")}
            </Row>
            <Row label="   Explanation source">{String(debug.explanation_source)}</Row>
            <Row label="   Evidence found in text">{String(debug.evidence_ok)}</Row>
            <Row label="2. Scam check">
              risk {letter.scam.risk} · {letter.scam.reasons.map((r) => r.reason_id).join(", ") || "no signals"}
            </Row>
            <Row label="3. Policy verdict">
              <strong className={debug.policy_allowed ? "text-ok" : "text-danger"}>
                {debug.policy_allowed ? "ALLOW" : "BLOCK"}
              </strong>
              {reasons.length > 0 && ` · ${reasons.join(", ")}`}
            </Row>
            {debug.match_score != null && (
              <Row label="   Merchant match score">{String(debug.match_score)}</Row>
            )}
            <Row label="4. Controller action">{letter.proposal.action}</Row>
            <Row label="   Total">{String(debug.total_ms)} ms</Row>
          </section>
        )}

        {steps.length > 0 && (
          <section className="flex flex-col gap-1">
            <h3 className="font-semibold">Bank calls (Nessie)</h3>
            {steps.map((step, index) => (
              <Row key={index} label={step.step ?? "call"}>
                {step.error
                  ? `error: ${step.error}`
                  : `${step.method} ${step.path} → ${step.status} · ${step.elapsed_ms} ms · request id ${step.request_id ?? "not sent by Nessie"}`}
              </Row>
            ))}
          </section>
        )}

        {log && (
          <section className="flex flex-col gap-1">
            <h3 className="font-semibold">
              Audit log ·{" "}
              <span className={log.chain_ok ? "text-ok" : "text-danger"}>
                {log.chain_ok ? "hash chain verified" : "HASH CHAIN BROKEN"}
              </span>
            </h3>
            <ol className="flex flex-col gap-1 font-mono text-xs">
              {log.events.map((event) => (
                <li key={event.hash} className="break-all">
                  #{event.seq} {event.actor}/{event.event}
                  {typeof event.data.reason === "string" && ` (${event.data.reason})`}{" "}
                  <span className="text-muted-foreground">
                    {event.prev_hash.slice(0, 8)}→{event.hash.slice(0, 8)}
                  </span>
                </li>
              ))}
            </ol>
          </section>
        )}

        <section aria-labelledby="jump-heading" className="flex flex-col gap-2">
          <h3 id="jump-heading" className="font-semibold text-muted-foreground">
            {t("en", "jump_to_screen")} (UI language: {lang})
          </h3>
          <div className="grid grid-cols-2 gap-2">
            {SCREENS.map((name) => (
              <DialogClose asChild key={name}>
                <Button
                  variant={name === screen ? "default" : "outline"}
                  aria-pressed={name === screen}
                  onClick={() => go(name)}
                >
                  {name}
                </Button>
              </DialogClose>
            ))}
          </div>
        </section>
      </DialogContent>
    </Dialog>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <p className="break-words">
      <span className="whitespace-pre text-muted-foreground">{label}: </span>
      {children}
    </p>
  );
}
