import {
  ChevronDown,
  CircleAlert,
  Loader,
  MessageCircleQuestion,
  Mic,
  Send,
  Square,
} from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { PlayButton } from "@/components/PlayButton";
import { Button } from "@/components/ui/button";
import { t, type Lang, type StringKey } from "@/i18n";
import { answerAudioUrl, ApiError, askLetter, type AskResult, type Letter } from "@/lib/api";
import { canRecord, MAX_RECORD_SECONDS, startRecording, type Recording } from "@/lib/recordWav";

type State = "idle" | "listening" | "thinking";

/**
 * Ask a question about the letter by voice or by typing.
 * The answer comes only from the letter and is shown as text with a Play
 * button. Asking can never pay anything: the server's answer route has no
 * way to reach the payment code.
 */
export function AskBox({ lang, letter }: { lang: Lang; letter: Letter }) {
  const [state, setState] = useState<State>("idle");
  const [typed, setTyped] = useState("");
  const [result, setResult] = useState<AskResult | null>(null);
  const [problem, setProblem] = useState<StringKey | null>(null);
  const recording = useRef<Recording | null>(null);
  const timer = useRef<number | null>(null);
  const micAvailable = canRecord();

  // Leaving the screen stops the microphone.
  useEffect(
    () => () => {
      recording.current?.cancel();
      if (timer.current) window.clearTimeout(timer.current);
    },
    [],
  );

  async function send(question: Blob | string) {
    setState("thinking");
    setProblem(null);
    try {
      setResult(await askLetter(letter.letter_id, question));
      setTyped("");
    } catch (error) {
      const unclear = error instanceof ApiError && error.reason === "question_unclear";
      setProblem(unclear ? "ask_unclear" : "ask_error");
    }
    setState("idle");
  }

  async function stopAndSend() {
    if (timer.current) window.clearTimeout(timer.current);
    const current = recording.current;
    recording.current = null;
    if (!current) return;
    try {
      await send(await current.stop());
    } catch {
      setProblem("ask_error");
      setState("idle");
    }
  }

  async function toggleMic() {
    if (state === "listening") {
      await stopAndSend();
      return;
    }
    setProblem(null);
    try {
      recording.current = await startRecording();
      setState("listening");
      // Stop by itself after a while so a forgotten recording is not sent forever.
      timer.current = window.setTimeout(stopAndSend, MAX_RECORD_SECONDS * 1000);
    } catch {
      setProblem("ask_mic_blocked"); // permission refused, or no microphone
    }
  }

  function submitTyped(event: FormEvent) {
    event.preventDefault();
    const question = typed.trim();
    if (question && state === "idle") void send(question);
  }

  const busy = state === "thinking";
  return (
    // Closed until opened, so the main screen stays calm. The content stays
    // mounted while closed, so a recording or answer is never lost.
    <details className="group rounded-2xl border border-hairline bg-surface shadow-card">
      <summary className="flex min-h-15 cursor-pointer list-none items-center gap-3 px-5 py-3 font-semibold [&::-webkit-details-marker]:hidden">
        <MessageCircleQuestion className="size-6 shrink-0 text-primary" aria-hidden="true" />
        <span className="grow">{t(lang, "ask_title")}</span>
        <ChevronDown
          className="size-5 shrink-0 text-muted-foreground transition-transform group-open:rotate-180"
          aria-hidden="true"
        />
      </summary>
      <div className="flex flex-col gap-4 border-t border-hairline px-5 py-5">
      {micAvailable && (
        <Button
          size="lg"
          variant={state === "listening" ? "default" : "outline"}
          aria-pressed={state === "listening"}
          disabled={busy}
          onClick={toggleMic}
        >
          {state === "listening" ? <Square aria-hidden="true" /> : <Mic aria-hidden="true" />}
          {t(lang, state === "listening" ? "ask_stop" : "ask_mic")}
        </Button>
      )}

      <form onSubmit={submitTyped} className="flex flex-wrap gap-2">
        <input
          type="text"
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          maxLength={300}
          disabled={state !== "idle"}
          placeholder={t(lang, "ask_placeholder")}
          aria-label={t(lang, "ask_placeholder")}
          className="min-h-12 min-w-[min(14rem,100%)] grow basis-56 rounded-xl border-[1.5px] border-control-border bg-background px-3.5 text-base"
        />
        <Button type="submit" disabled={state !== "idle" || !typed.trim()}>
          <Send className="rtl:-scale-x-100" aria-hidden="true" />
          {t(lang, "ask_send")}
        </Button>
      </form>

      {/* Announces progress, problems and the answer to screen readers. */}
      <div role="status" aria-live="polite" className="flex flex-col gap-3 empty:hidden">
        {state === "listening" && (
          <p className="flex items-center gap-2 font-semibold">
            <Mic className="size-5 shrink-0 text-danger" aria-hidden="true" />
            {t(lang, "ask_listening")}
          </p>
        )}
        {busy && (
          <p className="flex items-center gap-2 font-semibold">
            <Loader
              className="size-5 shrink-0 animate-spin motion-reduce:animate-none"
              aria-hidden="true"
            />
            {t(lang, "ask_thinking")}
          </p>
        )}
        {problem && (
          <p className="flex items-start gap-2 rounded-xl bg-danger-soft p-3 font-semibold text-danger">
            <CircleAlert className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
            {t(lang, problem)}
          </p>
        )}
        {result && !busy && (
          <div className="flex flex-col gap-2 rounded-xl bg-muted p-4">
            <p className="text-sm font-semibold text-muted-foreground">{t(lang, "you_asked")}</p>
            <p>
              <bdi>{result.question}</bdi>
            </p>
            <p className="text-sm font-semibold text-muted-foreground">{t(lang, "answer")}</p>
            <p lang={letter.language} className="text-lg leading-relaxed">
              {result.answer}
            </p>
            <PlayButton
              key={result.answer_id}
              lang={lang}
              audioUrl={answerAudioUrl(letter.letter_id, result.answer_id)}
              language={letter.language}
              text={result.answer}
            />
          </div>
        )}
      </div>

      <p className="m-0 text-sm text-muted-foreground">{t(lang, "ask_note")}</p>
      </div>
    </details>
  );
}
