import { ArrowRight, Camera, CircleAlert, CircleCheck, Loader, TriangleAlert, Zap } from "lucide-react";
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
    <div className="flex flex-col gap-6">
      <LanguagePicker lang={lang} onChange={onLangChange} />

      <div>
        <h1 className="text-2xl leading-snug font-bold">{t(lang, "capture_title")}</h1>
        <p className="mt-1 text-muted-foreground">{t(lang, "capture_intro")}</p>
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

      {/* One button that stays mounted (so focus is not lost) and changes label. */}
      <Button
        size={photo ? "default" : "lg"}
        variant={photo ? "outline" : "default"}
        disabled={preparing}
        onClick={() => fileInput.current?.click()}
      >
        <Camera aria-hidden="true" />
        {t(lang, photo ? "retake_photo" : "take_photo")}
      </Button>

      {/* Announces progress and results to screen readers. Always mounted. */}
      <LiveRegion className="empty:hidden">
        {preparing && (
          <p className="flex items-center gap-2 font-semibold">
            <Loader className="size-5 shrink-0 animate-spin" aria-hidden="true" />
            {t(lang, "preparing_photo")}
          </p>
        )}
        {photoState === "error" && (
          <p className="flex items-start gap-2 rounded-lg bg-danger-soft p-3 font-semibold text-danger">
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
        <Card className="gap-3">
          <img
            src={previewUrl}
            alt={t(lang, "photo_preview_alt")}
            className="max-h-80 w-full rounded-lg border bg-muted object-contain"
          />
          <p className="text-sm text-muted-foreground">
            {t(lang, "photo_size")}: <Num>{formatBytes(photo.size)}</Num>
          </p>
        </Card>
      )}

      {source && (
        <Button size="lg" onClick={handleContinue}>
          {t(lang, "continue")}
          <ArrowRight className="rtl:rotate-180" aria-hidden="true" />
        </Button>
      )}

      <section aria-labelledby="samples-heading" className="flex flex-col gap-2">
        <h2 id="samples-heading" className="font-semibold text-muted-foreground">
          {t(lang, "or_try_sample")}
        </h2>
        <SampleButton
          selected={sampleId === "electric_bill"}
          disabled={preparing}
          onClick={() => chooseSample("electric_bill")}
          icon={<Zap aria-hidden="true" />}
          label={t(lang, "sample_bill")}
        />
        <SampleButton
          selected={sampleId === "suspicious_letter"}
          disabled={preparing}
          onClick={() => chooseSample("suspicious_letter")}
          icon={<TriangleAlert aria-hidden="true" />}
          label={t(lang, "sample_suspicious")}
        />
      </section>
    </div>
  );
}

function SampleButton({
  selected,
  disabled,
  onClick,
  icon,
  label,
}: {
  selected: boolean;
  disabled: boolean;
  onClick: () => void;
  icon: ReactNode;
  label: string;
}) {
  return (
    <Button
      variant="outline"
      aria-pressed={selected}
      disabled={disabled}
      onClick={onClick}
      className={selected ? "justify-start border-primary bg-secondary" : "justify-start"}
    >
      {icon}
      <span className="grow text-start">{label}</span>
      {selected && <CircleCheck className="text-primary" aria-hidden="true" />}
    </Button>
  );
}
