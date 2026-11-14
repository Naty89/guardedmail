import { ArrowLeft, Check, ListChecks } from "lucide-react";
import { useEffect } from "react";

import { Num } from "@/components/Num";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { t } from "@/i18n";
import { formatCents } from "@/lib/format";
import type { ScreenProps } from "@/lib/screens";

/** Receipt after a confirmed mock payment. The demo-bank tag stays in view above. */
export function ReceiptScreen({ lang, go, receipt }: ScreenProps) {
  useEffect(() => {
    if (!receipt) go("capture");
  }, [receipt, go]);
  if (!receipt) return null;

  return (
    <div className="flex flex-col gap-5">
      <h1 className="sr-only">{t(lang, "receipt")}</h1>

      <Card className="items-center gap-0 p-0 text-center">
        <div className="flex w-full flex-col items-center gap-3 px-6 pt-8 pb-6">
          <span className="flex size-14 items-center justify-center rounded-full bg-ok-soft text-ok">
            <Check className="size-8" strokeWidth={2.5} aria-hidden="true" />
          </span>
          <p className="m-0 font-serif-display text-2xl font-semibold text-ok">
            {t(lang, "payment_done")}
          </p>
          <p className="m-0 font-serif-display text-5xl leading-none font-semibold">
            <Num>{formatCents(receipt.amount_cents)}</Num>
          </p>
        </div>

        {/* Perforated edge, like a torn receipt. */}
        <div className="w-full border-t-2 border-dashed border-hairline" aria-hidden="true" />

        <dl className="m-0 grid w-full grid-cols-1 gap-4 px-6 py-5 text-start">
          <Row label={t(lang, "paid_to")}>
            <bdi>{receipt.payee_name}</bdi>
          </Row>
          <Row label={t(lang, "balance_left")}>
            <Num>{formatCents(receipt.new_balance_cents)}</Num>
          </Row>
        </dl>

        <p className="m-0 w-full border-t border-hairline px-6 py-3 text-center text-xs text-muted-foreground">
          {t(lang, "reference")}:{" "}
          <Num className="font-mono break-all">{receipt.nessie_id}</Num>
        </p>
      </Card>

      <nav className="flex flex-wrap justify-between gap-x-2 border-t border-hairline pt-4">
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

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="shrink-0 text-sm font-semibold text-muted-foreground">{label}</dt>
      <dd className="m-0 text-end font-semibold">{children}</dd>
    </div>
  );
}
