import { Check } from "lucide-react";

import { LANGUAGES, dirFor, t, type Lang } from "@/i18n";
import { cn } from "@/lib/utils";

/** Nine pills, each showing a language in its own script. */
export function LanguagePicker({ lang, onChange }: { lang: Lang; onChange: (lang: Lang) => void }) {
  return (
    <fieldset className="m-0 border-0 p-0">
      <legend className="mb-2.5 p-0 text-sm font-semibold text-muted-foreground">
        {t(lang, "choose_language")}
      </legend>
      <div className="flex flex-wrap gap-2">
        {LANGUAGES.map(({ code, name }) => {
          const selected = code === lang;
          return (
            <button
              key={code}
              type="button"
              lang={code}
              dir={dirFor(code)}
              aria-pressed={selected}
              onClick={() => onChange(code)}
              className={cn(
                "inline-flex min-h-12 cursor-pointer items-center justify-center gap-1.5 rounded-full border-[1.5px] px-4 text-base leading-snug transition-colors",
                selected
                  ? "border-primary bg-primary font-semibold text-primary-foreground"
                  : "border-control-border bg-surface font-medium hover:bg-primary-soft",
              )}
            >
              {/* The tick means selection is never shown by colour alone. */}
              {selected && <Check className="size-4 shrink-0" strokeWidth={3} aria-hidden="true" />}
              {name}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
