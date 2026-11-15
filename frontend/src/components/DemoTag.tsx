import { Landmark } from "lucide-react";

import { t, type Lang } from "@/i18n";

/** Always-visible reminder that all money in this app is mock money. */
export function DemoTag({ lang }: { lang: Lang }) {
  return (
    <div className="on-dark sticky top-0 z-30 bg-ink pt-[env(safe-area-inset-top)] text-white">
      <p className="mx-auto flex min-h-9 max-w-xl items-center justify-center gap-2 px-4 py-1 text-center text-sm leading-snug font-semibold text-balance">
        <Landmark className="size-4 shrink-0 text-accent" aria-hidden="true" />
        {t(lang, "demo_bank_tag")}
      </p>
    </div>
  );
}
