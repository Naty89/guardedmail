import { PlaceholderScreen } from "@/components/PlaceholderScreen";
import { t } from "@/i18n";
import type { ScreenProps } from "@/lib/screens";

/**
 * PLACEHOLDER (M5): the user confirms or rejects the ONE proposed action.
 * To build: show t(lang, "confirm_pay_question", { amount, merchant }) with
 * amounts from formatCents() (wrap stand-alone amounts in <Num>), then two
 * big buttons: "yes_pay" -> confirmProposal(id, token), "no_dont_pay" ->
 * rejectProposal(id). Nothing is paid without the explicit Yes tap.
 */
export function ConfirmScreen({ lang, go }: ScreenProps) {
  return (
    <PlaceholderScreen
      lang={lang}
      title={t(lang, "confirm_title")}
      milestone="M5"
      onBack={() => go("explanation")}
    />
  );
}
