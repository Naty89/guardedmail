import { Num } from "@/components/Num";
import { t, type Lang } from "@/i18n";
import type { Letter } from "@/lib/api";
import { formatDate } from "@/lib/dates";
import { formatCents } from "@/lib/format";

/**
 * The key facts as the reader saw them: sender, amount, due date.
 * The sender name is text from the letter, so it is shown in <bdi> and is
 * never used for the payment itself.
 */
export function LetterFacts({ lang, letter }: { lang: Lang; letter: Letter }) {
  const { sender, amount_cents, due_date } = letter.summary;
  return (
    <dl className="grid grid-cols-1 gap-3">
      <Fact label={t(lang, "who_sent_it")}>
        {sender ? <bdi>{sender}</bdi> : t(lang, "not_clear")}
      </Fact>
      {amount_cents !== null && (
        <Fact label={t(lang, "amount")}>
          <Num>{formatCents(amount_cents)}</Num>
        </Fact>
      )}
      {due_date !== null && (
        <Fact label={t(lang, "due_date")}>
          <Num>{formatDate(due_date, lang)}</Num>
        </Fact>
      )}
    </dl>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg bg-muted px-4 py-3">
      <dt className="text-sm font-semibold text-muted-foreground">{label}</dt>
      <dd className="text-xl font-bold">{children}</dd>
    </div>
  );
}
