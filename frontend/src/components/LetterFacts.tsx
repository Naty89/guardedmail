import { Num } from "@/components/Num";
import { t, type Lang } from "@/i18n";
import type { Letter } from "@/lib/api";
import { formatDate } from "@/lib/dates";
import { formatCents } from "@/lib/format";

/**
 * The key facts as the reader saw them: sender, amount, due date, laid out
 * like the summary box on a statement. The sender name is text from the
 * letter, so it is shown in <bdi> and is never used for the payment itself.
 */
export function LetterFacts({ lang, letter }: { lang: Lang; letter: Letter }) {
  const { sender, amount_cents, due_date } = letter.summary;
  const hasNumbers = amount_cents !== null || due_date !== null;
  return (
    <dl className="m-0 overflow-hidden rounded-xl border border-hairline bg-background">
      <Fact label={t(lang, "who_sent_it")}>
        <span className="font-heading text-xl">
          {sender ? <bdi>{sender}</bdi> : t(lang, "not_clear")}
        </span>
      </Fact>
      {hasNumbers && (
        <div className="grid grid-cols-[auto_minmax(0,1fr)] divide-x divide-hairline border-t border-hairline rtl:divide-x-reverse big:grid-cols-1 big:divide-x-0 big:divide-y">
          {amount_cents !== null && (
            <Fact label={t(lang, "amount")}>
              <span className="font-heading text-2xl">
                <Num>{formatCents(amount_cents)}</Num>
              </span>
            </Fact>
          )}
          {due_date !== null && (
            <Fact label={t(lang, "due_date")}>
              <span className="font-heading text-lg">
                <Num dir="auto">{formatDate(due_date, lang)}</Num>
              </span>
            </Fact>
          )}
        </div>
      )}
    </dl>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="px-4 py-3">
      <dt className="text-sm font-semibold text-muted-foreground">{label}</dt>
      <dd className="m-0 mt-0.5 leading-snug font-semibold">{children}</dd>
    </div>
  );
}
