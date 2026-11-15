import { Check, SlidersHorizontal } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { t, type Lang, type StringKey } from "@/i18n";
import { CONTRASTS, TEXT_SIZES, type Contrast, type Prefs, type TextSize } from "@/lib/prefs";
import { cn } from "@/lib/utils";

/** Header button that opens the text size and colour settings. */
export function DisplaySettings({
  lang,
  prefs,
  onChange,
}: {
  lang: Lang;
  prefs: Prefs;
  onChange: (prefs: Prefs) => void;
}) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          aria-label={t(lang, "display_settings")}
          className="flex size-12 cursor-pointer items-center justify-center rounded-full text-ink hover:bg-primary-soft"
        >
          <SlidersHorizontal className="size-6" aria-hidden="true" />
        </button>
      </DialogTrigger>
      <DialogContent closeLabel={t(lang, "close")}>
        <DialogTitle>{t(lang, "display_settings")}</DialogTitle>
        <DialogDescription className="sr-only">
          {t(lang, "text_size")}, {t(lang, "contrast")}
        </DialogDescription>

        <Group legend={t(lang, "text_size")}>
          {TEXT_SIZES.map((size) => (
            <Choice
              key={size}
              selected={prefs.size === size}
              onClick={() => onChange({ ...prefs, size: size as TextSize })}
            >
              {t(lang, `size_${size}` as StringKey)}
            </Choice>
          ))}
        </Group>

        <Group legend={t(lang, "contrast")}>
          {CONTRASTS.map((contrast) => (
            <Choice
              key={contrast}
              selected={prefs.contrast === contrast}
              onClick={() => onChange({ ...prefs, contrast: contrast as Contrast })}
            >
              {t(lang, `contrast_${contrast}` as StringKey)}
            </Choice>
          ))}
        </Group>
      </DialogContent>
    </Dialog>
  );
}

function Group({ legend, children }: { legend: string; children: React.ReactNode }) {
  return (
    <fieldset className="m-0 border-0 p-0">
      <legend className="mb-2.5 p-0 text-sm font-semibold text-muted-foreground">{legend}</legend>
      <div className="flex flex-wrap gap-2">{children}</div>
    </fieldset>
  );
}

function Choice({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={cn(
        "inline-flex min-h-12 cursor-pointer items-center justify-center gap-1.5 rounded-full border-[1.5px] px-4 text-base leading-snug transition-colors",
        selected
          ? "border-primary bg-primary font-semibold text-primary-foreground"
          : "border-control-border bg-surface font-medium hover:bg-primary-soft",
      )}
    >
      {/* The tick means the choice is never shown by colour alone. */}
      {selected && <Check className="size-4 shrink-0" strokeWidth={3} aria-hidden="true" />}
      {children}
    </button>
  );
}
