import { CircleAlert, Loader } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { t, type StringKey } from "@/i18n";
import { confirmProposal, letterImageUrl, rejectProposal } from "@/lib/api";
import { formatCents } from "@/lib/format";
import type { ScreenProps } from "@/lib/screens";

/** Plain-words message for each reason the server may refuse a payment. */
function blockedMessage(reason: string | null): StringKey {
  if (reason === "token_expired") return "payment_expired";
  if (reason === "already_paid" || reason === "token_reused") return "already_paid";
  return "payment_failed";
}

/**
 * The confirm dialog. Nothing is paid unless the user taps "Yes, pay".
 * - The keyboard focus starts on "No, don't pay".
 * - Both buttons are the same size.
 * - Closing the dialog (X or Escape) pays nothing.
 * - Only the proposal id and its token go to the server. The amount and the
 *   merchant shown here are for the user to read; the server uses its own copy.
 */
export function ConfirmScreen({ lang, go, letter, setLetter, setReceipt }: ScreenProps) {
  const noButton = useRef<HTMLButtonElement>(null);
  const [state, setState] = useState<"asking" | "paying" | "blocked">("asking");
  const [message, setMessage] = useState<StringKey | null>(null);

  const proposal = letter?.proposal;
  const payable =
    letter && proposal?.action === "pay" && proposal.token && proposal.amount_cents !== null;

  useEffect(() => {
    if (!payable) go(letter ? "explanation" : "capture");
  }, [payable, letter, go]);
  if (!payable || !letter || !proposal?.token || proposal.amount_cents === null) return null;

  const amount = formatCents(proposal.amount_cents);
  const merchant = proposal.payee_name ?? "";
  const token = proposal.token;

  async function pay() {
    setState("paying");
    try {
      const result = await confirmProposal(proposal!.id, token);
      if (result.status === "paid" && result.receipt) {
        setReceipt(result.receipt);
        go("receipt");
        return;
      }
      setMessage(blockedMessage(result.block_reason));
    } catch {
      setMessage("payment_failed");
    }
    setState("blocked");
  }

  function decline() {
    // Tell the server so this proposal can never be confirmed later.
    rejectProposal(proposal!.id).catch(() => undefined);
    // Take the pay option off the screen too: this proposal is finished.
    setLetter({
      ...letter!,
      proposal: { ...proposal!, action: "ask_user", token: null, block_reason: "proposal_rejected" },
    });
    go("explanation");
  }

  return (
    <Dialog open onOpenChange={(open) => !open && state !== "paying" && go("explanation")}>
      <DialogContent
        closeLabel={t(lang, "close")}
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          noButton.current?.focus(); // the cautious choice gets the focus
        }}
      >
        <DialogTitle>{t(lang, "confirm_title")}</DialogTitle>

        <div className="flex items-start gap-4">
          <img
            src={letterImageUrl(letter.letter_id)}
            alt={t(lang, "letter_photo_alt")}
            className="h-32 w-24 shrink-0 rounded-lg border bg-muted object-cover object-top"
            onError={(event) => (event.currentTarget.style.display = "none")} // an old letter may have no picture
          />
          <DialogDescription className="text-xl leading-snug font-semibold text-foreground">
            {t(lang, "confirm_pay_question", { amount, merchant })}
          </DialogDescription>
        </div>

        <div role="status" aria-live="polite" className="empty:hidden">
          {state === "paying" && (
            <p className="flex items-center gap-2 font-semibold">
              <Loader
                className="size-5 shrink-0 animate-spin motion-reduce:animate-none"
                aria-hidden="true"
              />
              {t(lang, "paying")}
            </p>
          )}
          {state === "blocked" && message && (
            <p className="flex items-start gap-2 rounded-lg bg-danger-soft p-3 font-semibold text-danger">
              <CircleAlert className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
              {t(lang, message)}
            </p>
          )}
        </div>

        {state === "blocked" ? (
          <Button size="lg" variant="outline" onClick={() => go("explanation")}>
            {t(lang, "back")}
          </Button>
        ) : (
          <div className="grid grid-cols-1 gap-3">
            {/* Same size on purpose: neither answer is made easier to tap. */}
            <Button size="lg" disabled={state === "paying"} onClick={pay}>
              {t(lang, "yes_pay", { amount })}
            </Button>
            <Button
              ref={noButton}
              size="lg"
              variant="outline"
              disabled={state === "paying"}
              onClick={decline}
            >
              {t(lang, "no_dont_pay")}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
