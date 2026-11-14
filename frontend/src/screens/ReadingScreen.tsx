import { ArrowLeft, CircleAlert, Loader, RotateCw } from "lucide-react";
import { useEffect, useState } from "react";

import { LiveRegion } from "@/components/LiveRegion";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { t, type StringKey } from "@/i18n";
import { ApiError, postLetter } from "@/lib/api";
import type { ScreenProps } from "@/lib/screens";

// Server reasons that mean "the photo is the problem, take another one".
const PHOTO_PROBLEMS = ["image_unreadable", "image_too_large", "image_empty"];

/**
 * Sends the letter to the server and waits. The server does the reading and
 * the scam check in one request, so the step text simply changes after a few
 * seconds to show that work is still going on.
 */
export function ReadingScreen({ lang, go, source, setLetter }: ScreenProps) {
  const [step, setStep] = useState<"reading" | "checking_scams">("reading");
  const [error, setError] = useState<StringKey | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!source) {
      go("capture");
      return;
    }
    let cancelled = false;
    setError(null);
    setStep("reading");
    setLetter(null);
    const timer = window.setTimeout(() => setStep("checking_scams"), 2500);

    postLetter(source, lang)
      .then((letter) => {
        if (cancelled) return;
        setLetter(letter);
        // A flagged letter goes to the scam screen, which has no pay button.
        go(letter.proposal.action === "flag" ? "scam_blocked" : "explanation");
      })
      .catch((problem: unknown) => {
        if (cancelled) return;
        const reason = problem instanceof ApiError ? problem.reason : null;
        setError(reason && PHOTO_PROBLEMS.includes(reason) ? "photo_unclear" : "reading_error");
      })
      .finally(() => window.clearTimeout(timer));

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
    // Runs once per attempt. `lang` and `source` are fixed while this screen shows.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <h1 className="text-2xl leading-snug font-bold">{t(lang, "reading")}</h1>
        {/* Stays mounted; only its text changes, so screen readers announce each step. */}
        <LiveRegion className="flex items-start gap-2 font-semibold">
          {error ? (
            <>
              <CircleAlert className="mt-0.5 size-6 shrink-0 text-danger" aria-hidden="true" />
              <span className="text-danger">{t(lang, error)}</span>
            </>
          ) : (
            <>
              <Loader
                className="mt-0.5 size-6 shrink-0 animate-spin motion-reduce:animate-none"
                aria-hidden="true"
              />
              <span>{t(lang, step)}</span>
            </>
          )}
        </LiveRegion>
      </Card>

      {error && (
        <Button size="lg" onClick={() => setAttempt((n) => n + 1)}>
          <RotateCw aria-hidden="true" />
          {t(lang, "try_again")}
        </Button>
      )}
      <Button variant="outline" onClick={() => go("capture")}>
        <ArrowLeft className="rtl:rotate-180" aria-hidden="true" />
        {t(lang, "back")}
      </Button>
    </div>
  );
}
