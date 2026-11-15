import { Download, Share, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { t, type Lang } from "@/i18n";

const STORAGE_KEY = "guarded.installHint";

/** The event Chrome on Android fires when the app can be installed. */
type InstallPrompt = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

/** True when the app is already running from the home screen. */
function isInstalled(): boolean {
  const iosFlag = (navigator as Navigator & { standalone?: boolean }).standalone === true;
  return iosFlag || window.matchMedia?.("(display-mode: standalone)").matches === true;
}

function isIphoneOrIpad(): boolean {
  // iPadOS reports itself as a Mac, so also look for a touch screen.
  return (
    /iPhone|iPad|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

function wasDismissed(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "dismissed";
  } catch {
    return false; // storage blocked: just show it again next visit
  }
}

/**
 * Tells people how to put the app on their home screen.
 * - iPhone and iPad: Safari cannot be asked to install, so show the two taps.
 * - Android Chrome: offer a real "Install the app" button.
 * - Anywhere else, once installed, or after "Not now": shows nothing.
 */
export function InstallHint({ lang }: { lang: Lang }) {
  const [ios] = useState(isIphoneOrIpad);
  const [hidden, setHidden] = useState(() => isInstalled() || wasDismissed());
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null);

  useEffect(() => {
    function onPrompt(event: Event) {
      event.preventDefault(); // keep Chrome's own banner from appearing; we show ours
      setPrompt(event as InstallPrompt);
    }
    function onInstalled() {
      setHidden(true);
    }
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  function dismiss() {
    setHidden(true);
    try {
      window.localStorage.setItem(STORAGE_KEY, "dismissed");
    } catch {
      // Nothing to do: it will simply show again next time.
    }
  }

  async function install() {
    if (!prompt) return;
    await prompt.prompt();
    const choice = await prompt.userChoice;
    setPrompt(null);
    if (choice.outcome === "accepted") setHidden(true);
  }

  if (hidden || (!ios && !prompt)) return null;

  return (
    <aside className="flex flex-col gap-3 rounded-2xl border border-accent bg-accent-soft p-5 text-ink">
      <div className="flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-accent">
          {ios ? <Share className="size-5" aria-hidden="true" /> : <Download className="size-5" aria-hidden="true" />}
        </span>
        <div className="grow">
          <h2 className="m-0 text-lg leading-snug">{t(lang, "install_title")}</h2>
          <p className="m-0 mt-1">{t(lang, ios ? "install_ios" : "install_android")}</p>
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label={t(lang, "not_now")}
          className="-m-1.5 flex size-12 shrink-0 cursor-pointer items-center justify-center rounded-xl hover:bg-accent/40"
        >
          <X className="size-5" aria-hidden="true" />
        </button>
      </div>
      {!ios && prompt && (
        <Button onClick={install}>
          <Download aria-hidden="true" />
          {t(lang, "install_button")}
        </Button>
      )}
    </aside>
  );
}
