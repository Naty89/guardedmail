/** "2026-11-24" -> "24 Nov 2026" style in the user's language, Western digits. */
import type { Lang } from "@/i18n";

export function formatDate(isoDate: string, lang: Lang): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  if (!year || !month || !day) return isoDate;
  try {
    // "-u-nu-latn" forces digits 0-9 in every language.
    return new Intl.DateTimeFormat(`${lang}-u-nu-latn`, {
      year: "numeric",
      month: "long",
      day: "numeric",
      timeZone: "UTC",
    }).format(new Date(Date.UTC(year, month - 1, day)));
  } catch {
    return isoDate;
  }
}
