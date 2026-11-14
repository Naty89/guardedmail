import { Check, Languages } from "lucide-react";

import { LANGUAGES, dirFor, t, type Lang } from "@/i18n";
import { cn } from "@/lib/utils";

/** Nine buttons, each showing a language in its own script. */
export function LanguagePicker({ lang, onChange }: { lang: Lang; onChange: (lang: Lang) => void }) {
  return (
    <fieldset className="m-0 border-0 p-0">
      <legend className="mb-2 flex items-center gap-2 p-0 font-semibold">
        <Languages className="size-5 shrink-0 text-primary" aria-hidden="true" />
        {t(lang, "choose_language")}
      </legend>
      <div className="grid grid-cols-3 gap-2">
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
                "relative flex min-h-12 cursor-pointer items-center justify-center rounded-lg border-2 px-1 py-2 text-center text-[0.95rem] leading-snug transition-colors",
                selected
                  ? "border-primary bg-primary font-bold text-primary-foreground"
                  : "border-control-border bg-card font-medium hover:bg-secondary",
              )}
            >
              {/* The tick means selection is never shown by colour alone. */}
              {selected && (
                <Check
                  className="absolute end-0.5 top-0.5 size-3.5"
                  strokeWidth={3.5}
                  aria-hidden="true"
                />
              )}
              {name}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
