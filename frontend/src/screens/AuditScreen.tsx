import { PlaceholderScreen } from "@/components/PlaceholderScreen";
import { t } from "@/i18n";
import type { ScreenProps } from "@/lib/screens";

/**
 * PLACEHOLDER (M6): list of what the app did for this letter.
 * To build: getAudit(letterId) rendered as a simple time-ordered list.
 */
export function AuditScreen({ lang, go }: ScreenProps) {
  return (
    <PlaceholderScreen
      lang={lang}
      title={t(lang, "audit_log")}
      milestone="M6"
      onBack={() => go("capture")}
    />
  );
}
