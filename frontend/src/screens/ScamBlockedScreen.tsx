import { ArrowLeft } from "lucide-react";
import { useEffect } from "react";

import { LetterFacts } from "@/components/LetterFacts";
import { ScamStatus } from "@/components/ScamStatus";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { t } from "@/i18n";
import type { ScreenProps } from "@/lib/screens";

/**
 * Shown when the letter looks like a possible scam.
 * There is NO pay button on this screen, on purpose. Do not add one.
 * (M6 adds quotes from the letter to the reasons.)
 */
export function ScamBlockedScreen({ lang, go, letter }: ScreenProps) {
  useEffect(() => {
    if (!letter) go("capture");
  }, [letter, go]);
  if (!letter) return null;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl leading-snug font-bold">{t(lang, "explanation_title")}</h1>

      <ScamStatus lang={lang} scam={letter.scam} defaultOpen />
      <p className="text-lg font-semibold">{t(lang, "scam_blocked_body")}</p>

      <Card>
        <p lang={letter.language} className="text-lg leading-relaxed whitespace-pre-line">
          {letter.explanation}
        </p>
        <LetterFacts lang={lang} letter={letter} />
      </Card>

      <Button variant="outline" onClick={() => go("capture")}>
        <ArrowLeft className="rtl:rotate-180" aria-hidden="true" />
        {t(lang, "start_over")}
      </Button>
    </div>
  );
}
