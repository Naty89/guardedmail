import { Loader, Pause, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { t, VOICE_ENABLED, type Lang } from "@/i18n";
import { letterAudioUrl } from "@/lib/api";

// Voice codes for the browser's built-in speech, used when the server has no audio.
const SPEECH_LOCALE: Partial<Record<Lang, string>> = {
  en: "en-US",
  es: "es-ES",
  hi: "hi-IN",
  te: "te-IN",
  ta: "ta-IN",
  pt: "pt-BR",
};

type Source = { kind: "loading" } | { kind: "audio"; url: string } | { kind: "browser" };

/**
 * Play / Pause for the explanation. It never starts by itself.
 * The audio is fetched (not played) when the screen opens, so the tap can
 * start it straight away. If the server has no audio (204) the browser's own
 * voice reads the text. Shown only for languages with a tested voice.
 */
export function PlayButton({
  lang,
  letterId,
  language,
  text,
}: {
  lang: Lang;
  letterId: string;
  language: Lang;
  text: string;
}) {
  const [source, setSource] = useState<Source>({ kind: "loading" });
  const [playing, setPlaying] = useState(false);
  const [waiting, setWaiting] = useState(false); // tapped before the audio arrived
  const audio = useRef<HTMLAudioElement | null>(null);
  const enabled = VOICE_ENABLED.includes(language);

  // Fetch the audio file ahead of time. This loads it; it does not play it.
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let url: string | null = null;
    setSource({ kind: "loading" });
    fetch(letterAudioUrl(letterId))
      .then(async (response) => {
        if (response.status !== 200) throw new Error("no audio");
        url = URL.createObjectURL(await response.blob());
        if (!cancelled) setSource({ kind: "audio", url });
      })
      .catch(() => !cancelled && setSource({ kind: "browser" }));
    return () => {
      cancelled = true;
      audio.current?.pause();
      audio.current = null;
      window.speechSynthesis?.cancel();
      if (url) URL.revokeObjectURL(url);
    };
  }, [letterId, enabled]);

  function start(from: Source) {
    if (from.kind === "audio") {
      if (!audio.current) {
        audio.current = new Audio(from.url);
        audio.current.onended = () => setPlaying(false);
        audio.current.onpause = () => setPlaying(false);
        audio.current.onplay = () => setPlaying(true);
      }
      audio.current.play().catch(() => setPlaying(false));
    } else if (from.kind === "browser" && "speechSynthesis" in window) {
      const synth = window.speechSynthesis;
      if (synth.paused) {
        synth.resume();
      } else {
        synth.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = SPEECH_LOCALE[language] ?? "en-US";
        utterance.rate = 0.9;
        utterance.onend = () => setPlaying(false);
        utterance.onerror = () => setPlaying(false);
        synth.speak(utterance);
      }
      setPlaying(true);
    }
  }

  // The user tapped Play while the audio was still loading: start when it arrives.
  useEffect(() => {
    if (waiting && source.kind !== "loading") {
      setWaiting(false);
      start(source);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [waiting, source]);

  function toggle() {
    if (playing) {
      if (audio.current) audio.current.pause();
      else window.speechSynthesis?.pause();
      setPlaying(false);
    } else if (source.kind === "loading") {
      setWaiting(true);
    } else {
      start(source);
    }
  }

  if (!enabled) return null;
  if (source.kind === "browser" && !("speechSynthesis" in window)) return null;

  const Icon = waiting ? Loader : playing ? Pause : Play;
  return (
    <Button variant="outline" onClick={toggle} aria-pressed={playing} className="self-start">
      <Icon
        className={waiting ? "animate-spin motion-reduce:animate-none" : undefined}
        aria-hidden="true"
      />
      {t(lang, playing ? "pause" : "play")}
    </Button>
  );
}
