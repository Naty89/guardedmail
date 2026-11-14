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
          ? "rounded-2xl border border-danger/40 bg-danger-soft px-5 py-4"
          : "rounded-2xl border border-hairline bg-surface px-5 py-3.5"
      }
    >
      <p
        className={
          warning
            ? "flex items-center gap-2.5 font-serif-display text-xl font-semibold text-danger"
            : "flex items-center gap-2.5 font-semibold text-muted-foreground"
        }
      >
        {warning ? (
          <ShieldAlert className="size-6 shrink-0" aria-hidden="true" />
        ) : (
          <ShieldQuestion className="size-5 shrink-0" aria-hidden="true" />
        )}
        {t(lang, warning ? "possible_scam" : "no_warning_signs")}
      </p>

      {scam.reasons.length > 0 && (
        <details open={defaultOpen} className="mt-1">
          <summary className="flex min-h-12 cursor-pointer items-center font-semibold underline underline-offset-4">
            {t(lang, "why")}
          </summary>
          <ul className="m-0 flex list-none flex-col gap-3 p-0 pb-1">
            {scam.reasons.map((reason) => (
              <li key={reason.reason_id} className="border-s-2 border-danger/50 ps-3">
                <span className="font-medium">
                  {t(lang, `signal_${reason.reason_id}` as StringKey)}
                </span>
                {reason.quote && (
                  <q
                    className="mt-1 block text-sm leading-snug text-muted-foreground"
                    lang="en"
                    dir="ltr"
                  >
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
