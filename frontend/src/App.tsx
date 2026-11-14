import { Mail } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { BackendStatus } from "@/components/BackendStatus";
import { DemoTag } from "@/components/DemoTag";
import { JudgePanel } from "@/components/JudgePanel";
import { dirFor, loadLang, saveLang, t, type Lang } from "@/i18n";
import type { Letter, Receipt } from "@/lib/api";
import { isDebug } from "@/lib/debug";
import type { LetterSource, Screen, ScreenProps } from "@/lib/screens";
import { AuditScreen } from "@/screens/AuditScreen";
import { CaptureScreen } from "@/screens/CaptureScreen";
import { ConfirmScreen } from "@/screens/ConfirmScreen";
import { ExplanationScreen } from "@/screens/ExplanationScreen";
import { ReadingScreen } from "@/screens/ReadingScreen";
import { ReceiptScreen } from "@/screens/ReceiptScreen";
import { ScamBlockedScreen } from "@/screens/ScamBlockedScreen";

/**
 * App shell: demo-bank tag, header, and ONE screen at a time.
 * All state lives here in memory; there is no router and no state library.
 */
export default function App() {
  const [lang, setLang] = useState<Lang>(loadLang);
  const [screen, setScreen] = useState<Screen>("capture");
  const [source, setSource] = useState<LetterSource | null>(null);
  const [letter, setLetter] = useState<Letter | null>(null);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [debug] = useState(isDebug);
  const dir = dirFor(lang);

  // Keep <html> in step too: dialogs render outside our root element.
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = dir;
  }, [lang, dir]);

  // On a screen change, move keyboard / screen-reader focus to the new screen.
  const main = useRef<HTMLElement>(null);
  const firstRender = useRef(true);
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    main.current?.focus();
    window.scrollTo(0, 0);
  }, [screen]);

  function changeLang(next: Lang) {
    setLang(next);
    saveLang(next);
  }

  const props: ScreenProps = {
    lang,
    go: setScreen,
    source,
    letter,
    setLetter,
    receipt,
    setReceipt,
  };

  return (
    <div lang={lang} dir={dir} className="flex min-h-dvh flex-col">
      <DemoTag lang={lang} />

      <header className="mx-auto flex w-full max-w-xl flex-wrap items-center justify-between gap-x-3 gap-y-2 px-5 pt-5">
        {/* The wordmark: yellow mark, bold "Guarded", and "Mail" in a cobalt tag. */}
        <p className="m-0 flex items-center gap-2.5" lang="en" dir="ltr" aria-label={t(lang, "app_name")}>
          <span
            aria-hidden="true"
            className="flex size-10 shrink-0 items-center justify-center rounded-full bg-accent text-ink shadow-[0_3px_8px_-3px_rgb(18_27_56/0.55)]"
          >
            <Mail className="size-[1.35rem]" strokeWidth={2.25} />
          </span>
          <span aria-hidden="true" className="flex items-center gap-1.5 text-[1.5rem] leading-none font-bold">
            <span className="text-ink">Guarded</span>
            <span className="rounded-lg bg-primary px-2 py-0.5 text-white">Mail</span>
          </span>
        </p>
        <BackendStatus lang={lang} />
      </header>

      <main
        key={screen === "confirm" ? "explanation" : screen}
        ref={main}
        tabIndex={-1}
        className="screen-in mx-auto w-full max-w-xl grow px-5 pt-7 pb-24 outline-none"
      >
        {screen === "capture" && (
          <CaptureScreen {...props} onLangChange={changeLang} onSourceChange={setSource} />
        )}
        {screen === "reading" && <ReadingScreen {...props} />}
        {/* The confirm dialog opens on top of the explanation, which stays visible. */}
        {(screen === "explanation" || screen === "confirm") && <ExplanationScreen {...props} />}
        {screen === "confirm" && <ConfirmScreen {...props} />}
        {screen === "receipt" && <ReceiptScreen {...props} />}
        {screen === "scam_blocked" && <ScamBlockedScreen {...props} />}
        {screen === "audit" && <AuditScreen {...props} />}
      </main>

      {debug && <JudgePanel lang={lang} screen={screen} go={setScreen} letter={letter} />}
    </div>
  );
}
