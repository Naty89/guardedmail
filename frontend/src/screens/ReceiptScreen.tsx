import { ArrowLeft, ListChecks, CircleCheck } from "lucide-react";
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
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl leading-snug font-bold">{t(lang, "receipt")}</h1>

      <Card>
        <p className="flex items-center gap-2 text-xl font-bold text-ok">
          <CircleCheck className="size-7 shrink-0" aria-hidden="true" />
          {t(lang, "payment_done")}
        </p>
        <dl className="grid grid-cols-1 gap-3">
          <Row label={t(lang, "amount")}>
            <Num>{formatCents(receipt.amount_cents)}</Num>
          </Row>
          <Row label={t(lang, "paid_to")}>
            <bdi>{receipt.payee_name}</bdi>
          </Row>
          <Row label={t(lang, "balance_left")}>
            <Num>{formatCents(receipt.new_balance_cents)}</Num>
          </Row>
        </dl>
        <p className="text-sm break-all text-muted-foreground">
          {t(lang, "reference")}: <Num>{receipt.nessie_id}</Num>
        </p>
      </Card>

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

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg bg-muted px-4 py-3">
      <dt className="text-sm font-semibold text-muted-foreground">{label}</dt>
      <dd className="text-xl font-bold">{children}</dd>
    </div>
  );
}
