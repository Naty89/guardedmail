import {
  ArrowRight,
  Camera,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  History,
  Loader,
  TriangleAlert,
  X,
  Zap,
} from "lucide-react";
import { useEffect, useRef, useState, type ChangeEvent, type ReactNode } from "react";

import { InstallHint } from "@/components/InstallHint";
import { LanguagePicker } from "@/components/LanguagePicker";
import { LiveRegion } from "@/components/LiveRegion";
import { Num } from "@/components/Num";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { t, type Lang } from "@/i18n";
import { downscaleImage } from "@/lib/downscale";
import { formatBytes } from "@/lib/format";
import { MAX_PAGES, type LetterSource, type SampleId, type ScreenProps } from "@/lib/screens";
import { cn } from "@/lib/utils";

type Props = ScreenProps & {
  onLangChange: (lang: Lang) => void;
  onSourceChange: (source: LetterSource | null) => void;
};

type PhotoState = "idle" | "preparing" | "error";

/** First screen: pick a language, then take a photo or choose a sample letter. */
export function CaptureScreen({ lang, go, source, onLangChange, onSourceChange }: Props) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [photoState, setPhotoState] = useState<PhotoState>("idle");

  // Temporary URLs so <img> can show each downscaled page.
  const photos = source?.kind === "photo" ? source.images : [];
  const [previewUrls, setPreviewUrls] = useState<string[]>([]);
  useEffect(() => {
    const urls = photos.map((page) => URL.createObjectURL(page));
    setPreviewUrls(urls);
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
    // `photos` is a new array on every render, so depend on the source instead.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source]);

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ""; // lets the user pick the same file again
    if (!file) return;
    setPhotoState("preparing");
    try {
      const image = await downscaleImage(file);
      // A new photo is added after the pages already taken (a sample is replaced).
      onSourceChange({ kind: "photo", images: [...photos, image].slice(0, MAX_PAGES) });
      setPhotoState("idle");
    } catch {
      setPhotoState("error");
    }
  }

  function removePage(index: number) {
    const rest = photos.filter((_, i) => i !== index);
    onSourceChange(rest.length > 0 ? { kind: "photo", images: rest } : null);
  }

  function chooseSample(sampleId: SampleId) {
    // The server holds the sample images; we only send the id.
    setPhotoState("idle");
    onSourceChange({ kind: "sample", sampleId });
  }

  function handleContinue() {
    // The Reading screen sends the letter to the server and waits for the result.
    go("reading");
  }

  const sampleId = source?.kind === "sample" ? source.sampleId : null;
  const preparing = photoState === "preparing";

  return (
    <div className="flex flex-col gap-7">
      <LanguagePicker lang={lang} onChange={onLangChange} />

      <Card className="on-dark relative gap-5 overflow-hidden border-transparent bg-primary p-6 text-white">
        {/* Decorative shapes only. */}
        <span aria-hidden="true" className="pointer-events-none absolute -end-9 -top-9 size-28 rounded-full bg-accent" />
        <div className="relative">
          <h1 className="text-[1.75rem] leading-tight">{t(lang, "capture_title")}</h1>
          <p className="mt-2 text-on-primary-muted">{t(lang, "capture_intro")}</p>
        </div>

        {/* The real file input is hidden; the visible <button> opens it. */}
        <input
          ref={fileInput}
          type="file"
          accept="image/*"
          capture="environment"
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
          onChange={handleFile}
        />

        {/* Announces progress and results to screen readers. Always mounted. */}
        <LiveRegion className="empty:hidden">
          {preparing && (
            <p className="flex items-center gap-2 font-semibold">
              <Loader className="size-5 shrink-0 animate-spin" aria-hidden="true" />
              {t(lang, "preparing_photo")}
            </p>
          )}
          {photoState === "error" && (
            <p className="flex items-start gap-2 rounded-xl bg-danger-soft p-3 font-semibold text-danger">
              <CircleAlert className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
              {t(lang, "photo_error")}
            </p>
          )}
          {photos.length > 0 && (
            <p className="flex items-center gap-2 font-semibold text-white">
              <CircleCheck className="size-5 shrink-0 text-accent" aria-hidden="true" />
              {photos.length === 1
                ? t(lang, "photo_ready")
                : t(lang, "pages_ready", { n: photos.length })}
            </p>
          )}
          {sampleId && (
            <p className="flex items-center gap-2 font-semibold text-white">
              <CircleCheck className="size-5 shrink-0 text-accent" aria-hidden="true" />
              {t(lang, "sample_selected")}
            </p>
          )}
        </LiveRegion>

        {photos.length > 0 && (
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {previewUrls.map((url, index) => (
              <li key={url} className="flex items-center gap-3 rounded-xl bg-white/12 p-2">
                <img
                  src={url}
                  alt={t(lang, "photo_preview_alt")}
                  className="h-16 w-12 shrink-0 rounded-md border border-white/30 bg-surface object-cover object-top"
                />
                <span className="grow">
                  <span className="block font-semibold">{t(lang, "page_n", { n: index + 1 })}</span>
                  <span className="block text-sm text-on-primary-muted">
                    <Num>{formatBytes(photos[index]?.size ?? 0)}</Num>
                  </span>
                </span>
                <Button
                  variant="light"
                  size="icon"
                  aria-label={t(lang, "remove_page", { n: index + 1 })}
                  disabled={preparing}
                  onClick={() => removePage(index)}
                >
                  <X aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
        )}

        {/* The next step is always the one dominant button. */}
        {source ? (
          <>
            <Button size="lg" variant="accent" disabled={preparing} onClick={handleContinue}>
              {t(lang, "continue")}
              <ArrowRight className="rtl:rotate-180" aria-hidden="true" />
            </Button>
            {photos.length > 0 && photos.length < MAX_PAGES && (
              <>
                <Button
                  variant="light"
                  disabled={preparing}
                  onClick={() => fileInput.current?.click()}
                >
                  <Camera aria-hidden="true" />
                  {t(lang, "add_page")}
                </Button>
                <p className="m-0 text-sm text-on-primary-muted">{t(lang, "pages_hint")}</p>
              </>
            )}
            {photos.length === MAX_PAGES && (
              <p className="m-0 text-sm text-on-primary-muted">
                {t(lang, "max_pages", { n: MAX_PAGES })}
              </p>
            )}
          </>
        ) : (
          <Button
            size="lg"
            variant="accent"
            disabled={preparing}
            onClick={() => fileInput.current?.click()}
          >
            <Camera aria-hidden="true" />
            {t(lang, "take_photo")}
          </Button>
        )}
      </Card>

      <section aria-labelledby="samples-heading">
        <h2 id="samples-heading" className="mb-2.5 font-sans text-sm font-semibold text-muted-foreground">
          {t(lang, "or_try_sample")}
        </h2>
        <ul className="m-0 flex list-none flex-col overflow-hidden rounded-2xl border border-hairline bg-surface p-0 shadow-card">
          <SampleRow
            selected={sampleId === "electric_bill"}
            disabled={preparing}
            onClick={() => chooseSample("electric_bill")}
            icon={<Zap aria-hidden="true" />}
            label={t(lang, "sample_bill")}
          />
          <SampleRow
            selected={sampleId === "suspicious_letter"}
            disabled={preparing}
            onClick={() => chooseSample("suspicious_letter")}
            icon={<TriangleAlert aria-hidden="true" />}
            label={t(lang, "sample_suspicious")}
            divider
          />
        </ul>
      </section>

      <Button variant="outline" onClick={() => go("history")}>
        <History aria-hidden="true" />
        {t(lang, "my_letters")}
      </Button>

      <InstallHint lang={lang} />
    </div>
  );
}

function SampleRow({
  selected,
  disabled,
  onClick,
  icon,
  label,
  divider = false,
}: {
  selected: boolean;
  disabled: boolean;
  onClick: () => void;
  icon: ReactNode;
  label: string;
  divider?: boolean;
}) {
  return (
    <li className={cn(divider && "border-t border-hairline")}>
      <button
        type="button"
        aria-pressed={selected}
        disabled={disabled}
        onClick={onClick}
        className={cn(
          "flex min-h-15 w-full cursor-pointer items-center gap-3 px-4 py-2 text-start font-medium transition-colors hover:bg-primary-soft disabled:cursor-not-allowed disabled:opacity-60",
          selected && "bg-primary-soft",
        )}
      >
        <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-accent text-ink [&_svg]:size-[1.1rem]">
          {icon}
        </span>
        <span className="grow">{label}</span>
        {selected ? (
          <CircleCheck className="size-5 shrink-0 text-primary" aria-hidden="true" />
        ) : (
          <ChevronRight className="size-5 shrink-0 text-muted-foreground rtl:rotate-180" aria-hidden="true" />
        )}
      </button>
    </li>
  );
}
