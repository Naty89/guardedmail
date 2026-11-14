import { ArrowLeft, ListChecks } from "lucide-react";
import { useEffect } from "react";

import { AskBox } from "@/components/AskBox";
import { LetterFacts } from "@/components/LetterFacts";
import { PlayButton } from "@/components/PlayButton";
import { ScamStatus } from "@/components/ScamStatus";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { t } from "@/i18n";
import { letterAudioUrl } from "@/lib/api";
import type { ScreenProps } from "@/lib/screens";

/**
 * Shown when the letter looks like a possible scam.
 * There is NO pay button on this screen, on purpose. Do not add one.
 */
export function ScamBlockedScreen({ lang, go, letter }: ScreenProps) {
  useEffect(() => {
    if (!letter) go("capture");
  }, [letter, go]);
  if (!letter) return null;

  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-[1.75rem] leading-tight">{t(lang, "explanation_title")}</h1>

      <ScamStatus lang={lang} scam={letter.scam} defaultOpen />
      <p className="m-0 text-lg font-semibold">{t(lang, "scam_blocked_body")}</p>

      <Card className="gap-5">
        <p lang={letter.language} className="m-0 text-lg leading-relaxed whitespace-pre-line">
          {letter.explanation}
        </p>
        <PlayButton
          lang={lang}
          audioUrl={letterAudioUrl(letter.letter_id)}
          language={letter.language}
          text={letter.explanation}
        />
        <LetterFacts lang={lang} letter={letter} />
      </Card>

      <AskBox lang={lang} letter={letter} />

      <nav className="flex flex-wrap justify-between gap-x-2 border-t border-hairline pt-4">
        <Button variant="ghost" className="px-2" onClick={() => go("audit")}>
          <ListChecks aria-hidden="true" />
          {t(lang, "audit_log")}
        </Button>
        <Button variant="ghost" className="px-2" onClick={() => go("capture")}>
          <ArrowLeft className="rtl:rotate-180" aria-hidden="true" />
          {t(lang, "start_over")}
        </Button>
      </nav>
    </div>
  );
}
