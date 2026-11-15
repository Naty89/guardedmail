import {
  ArrowLeft,
  Ban,
  CircleCheck,
  CircleDot,
  Inbox,
  Loader,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";

import { LiveRegion } from "@/components/LiveRegion";
import { Num } from "@/components/Num";
import { Button } from "@/components/ui/button";
import { t, type Lang, type StringKey } from "@/i18n";
import { getHistory, openHistoryLetter, type HistoryItem, type HistoryStatus } from "@/lib/api";
import { formatDate } from "@/lib/dates";
import { formatCents } from "@/lib/format";
import type { ScreenProps } from "@/lib/screens";
import { cn } from "@/lib/utils";

/** Icon, word and colour for each status, so it is never shown by colour alone. */
const STATUS: Record<HistoryStatus, { icon: LucideIcon; key: StringKey; style: string }> = {
  paid: { icon: CircleCheck, key: "status_paid", style: "bg-ok-soft text-ok" },
  flagged: { icon: ShieldAlert, key: "possible_scam", style: "bg-danger text-white" },
  declined: { icon: Ban, key: "status_declined", style: "bg-muted text-muted-foreground" },
  open: { icon: CircleDot, key: "status_open", style: "bg-primary-soft text-primary-ink" },
  info: { icon: Inbox, key: "status_info", style: "bg-muted text-muted-foreground" },
};

/** The day a letter was read, in the user's language, with Western digits. */
function readOn(iso: string, lang: Lang): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  try {
    return new Intl.DateTimeFormat(`${lang}-u-nu-latn`, { month: "short", day: "numeric" }).format(date);
  } catch {
    return date.toISOString().slice(0, 10);
  }
}

/** Every letter read on this server, newest first. Tap one to open it again. */
export function HistoryScreen({ lang, go, setLetter }: ScreenProps) {
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [opening, setOpening] = useState<string | null>(null);
  const [problem, setProblem] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getHistory()
      .then((result) => !cancelled && setItems(result.items))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, []);

  async function open(item: HistoryItem) {
    setOpening(item.letter_id);
    setProblem(false);
    try {
      const letter = await openHistoryLetter(item.letter_id);
      setLetter(letter);
      go(letter.proposal.action === "flag" ? "scam_blocked" : "explanation");
    } catch {
      setProblem(true);
      setOpening(null);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-[1.75rem] leading-tight">{t(lang, "my_letters")}</h1>
        <p className="mt-1 text-muted-foreground">{t(lang, "history_intro")}</p>
      </div>

      <LiveRegion className="empty:hidden">
        {!items && !failed && (
          <p className="flex items-center gap-2 font-semibold">
            <Loader className="size-5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            {t(lang, "checking_connection")}
          </p>
        )}
        {failed && <p className="font-semibold text-danger">{t(lang, "reading_error")}</p>}
        {problem && (
          <p className="rounded-xl bg-danger-soft p-3 font-semibold text-danger">
            {t(lang, "history_open_error")}
          </p>
        )}
        {opening && !problem && (
          <p className="flex items-center gap-2 font-semibold">
            <Loader className="size-5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            {t(lang, "opening")}
          </p>
        )}
      </LiveRegion>

      {items && items.length === 0 && (
        <p className="rounded-2xl border border-hairline bg-surface p-5 text-muted-foreground">
          {t(lang, "history_empty")}
        </p>
      )}

      {items && items.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-3 p-0">
          {items.map((item) => (
            <li key={item.letter_id}>
              <HistoryCard lang={lang} item={item} disabled={opening !== null} onOpen={() => open(item)} />
            </li>
          ))}
        </ul>
      )}

      <Button variant="ghost" onClick={() => go("capture")}>
        <ArrowLeft className="rtl:rotate-180" aria-hidden="true" />
        {t(lang, "back")}
      </Button>
    </div>
  );
}

function HistoryCard({
  lang,
  item,
  disabled,
  onOpen,
}: {
  lang: Lang;
  item: HistoryItem;
  disabled: boolean;
  onOpen: () => void;
}) {
  const status = STATUS[item.status];
  const Icon = status.icon;
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onOpen}
      className="flex min-h-15 w-full cursor-pointer flex-col gap-2 rounded-2xl border border-hairline bg-surface p-4 text-start shadow-card transition-colors hover:bg-primary-soft disabled:cursor-not-allowed disabled:opacity-60"
    >
      <span className="flex items-start justify-between gap-3">
        <span className="text-lg leading-snug font-semibold">
          {item.sender ? <bdi>{item.sender}</bdi> : t(lang, "not_clear")}
        </span>
        <span
          className={cn(
            "inline-flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1 text-sm leading-snug font-semibold",
            status.style,
          )}
        >
          <Icon className="size-4 shrink-0" aria-hidden="true" />
          {t(lang, status.key)}
        </span>
      </span>
      <span className="flex flex-wrap items-baseline gap-x-4 gap-y-0.5 text-muted-foreground">
        {item.amount_cents !== null && (
          <span className="font-semibold text-foreground">
            <Num>{formatCents(item.amount_cents)}</Num>
          </span>
        )}
        {item.due_date && (
          <span>
            {t(lang, "due_date")}: <Num dir="auto">{formatDate(item.due_date, lang)}</Num>
          </span>
        )}
        <span className="text-sm">
          <Num dir="auto">{readOn(item.ts, lang)}</Num>
        </span>
      </span>
    </button>
  );
}
