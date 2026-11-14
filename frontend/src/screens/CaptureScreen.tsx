import {
  ArrowRight,
  Camera,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  Loader,
  TriangleAlert,
  Zap,
} from "lucide-react";
import { useEffect, useRef, useState, type ChangeEvent, type ReactNode } from "react";

import { LanguagePicker } from "@/components/LanguagePicker";
import { LiveRegion } from "@/components/LiveRegion";
import { Num } from "@/components/Num";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { t, type Lang } from "@/i18n";
import { downscaleImage } from "@/lib/downscale";
import { formatBytes } from "@/lib/format";
import type { LetterSource, SampleId, ScreenProps } from "@/lib/screens";
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

  // A temporary URL so <img> can show the downscaled photo.
  const photo = source?.kind === "photo" ? source.image : null;
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!photo) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(photo);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ""; // lets the user pick the same file again
    if (!file) return;
    setPhotoState("preparing");
    onSourceChange(null);
    try {
      const image = await downscaleImage(file);
      onSourceChange({ kind: "photo", image });
      setPhotoState("idle");
    } catch {
      setPhotoState("error");
    }
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

      <Card className="gap-5 p-6">
        <div>
          <h1 className="text-[1.75rem] leading-tight">{t(lang, "capture_title")}</h1>
          <p className="mt-2 text-muted-foreground">{t(lang, "capture_intro")}</p>
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
          {photo && (
            <p className="flex items-center gap-2 font-semibold text-ok">
              <CircleCheck className="size-5 shrink-0" aria-hidden="true" />
              {t(lang, "photo_ready")}
            </p>
          )}
          {sampleId && (
            <p className="flex items-center gap-2 font-semibold text-ok">
              <CircleCheck className="size-5 shrink-0" aria-hidden="true" />
              {t(lang, "sample_selected")}
            </p>
          )}
        </LiveRegion>

        {photo && previewUrl && (
          <div className="flex items-center gap-4 rounded-xl bg-muted p-3">
            <img
              src={previewUrl}
              alt={t(lang, "photo_preview_alt")}
              className="h-24 w-[4.5rem] shrink-0 rounded-md border border-hairline bg-surface object-cover object-top"
            />
            <p className="text-sm text-muted-foreground">
              {t(lang, "photo_size")}: <Num>{formatBytes(photo.size)}</Num>
            </p>
          </div>
        )}

        {/* The next step is always the one dominant button. */}
        {source ? (
          <>
            <Button size="lg" onClick={handleContinue}>
              {t(lang, "continue")}
              <ArrowRight className="rtl:rotate-180" aria-hidden="true" />
            </Button>
            <Button
              variant="ghost"
              disabled={preparing}
              onClick={() => fileInput.current?.click()}
            >
              <Camera aria-hidden="true" />
              {t(lang, "retake_photo")}
            </Button>
          </>
        ) : (
          <Button size="lg" disabled={preparing} onClick={() => fileInput.current?.click()}>
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
        <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary-soft text-primary [&_svg]:size-[1.1rem]">
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
