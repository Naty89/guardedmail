import { ShieldAlert, ShieldQuestion } from "lucide-react";

import { t, type Lang, type StringKey } from "@/i18n";
import type { ScamResult } from "@/lib/api";

/**
 * Scam check result as icon + word + colour, with a "Why?" list.
 * The wording is only ever "Possible scam" or "No warning signs found".
 * It never says a letter is safe, legitimate or verified.
 */
export function ScamStatus({
  lang,
  scam,
  defaultOpen = false,
}: {
  lang: Lang;
  scam: ScamResult;
  defaultOpen?: boolean;
}) {
  const warning = scam.risk !== "low";
  return (
    <div
      className={
        warning
          ? "rounded-xl border-2 border-danger bg-danger-soft p-4"
          : "rounded-xl border bg-card p-4"
      }
    >
      <p
        className={
          warning
            ? "flex items-center gap-2 text-xl font-bold text-danger"
            : "flex items-center gap-2 font-semibold"
        }
      >
        {warning ? (
          <ShieldAlert className="size-7 shrink-0" aria-hidden="true" />
        ) : (
          <ShieldQuestion className="size-6 shrink-0" aria-hidden="true" />
        )}
        {t(lang, warning ? "possible_scam" : "no_warning_signs")}
      </p>

      {scam.reasons.length > 0 && (
        <details open={defaultOpen} className="mt-2">
          <summary className="flex min-h-12 cursor-pointer items-center font-semibold underline">
            {t(lang, "why")}
          </summary>
          <ul className="list-disc space-y-2 ps-6 pt-1">
            {scam.reasons.map((reason) => (
              <li key={reason.reason_id}>
                {t(lang, `signal_${reason.reason_id}` as StringKey)}
                {reason.quote && (
                  <q className="mt-1 block text-muted-foreground" lang="en" dir="ltr">
                    {reason.quote}
                  </q>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
