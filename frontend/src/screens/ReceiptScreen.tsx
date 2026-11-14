import { PlaceholderScreen } from "@/components/PlaceholderScreen";
import { t } from "@/i18n";
import type { ScreenProps } from "@/lib/screens";

/**
 * PLACEHOLDER (M5): receipt after a mock payment.
 * To build: amount, merchant, new balance from getAccount(), a link to the
 * audit log, and a button back to Capture. Keep the demo-bank tag in view.
 */
export function ReceiptScreen({ lang, go }: ScreenProps) {
  return (
    <PlaceholderScreen
      lang={lang}
      title={t(lang, "receipt")}
      milestone="M5"
      onBack={() => go("capture")}
    />
  );
}
