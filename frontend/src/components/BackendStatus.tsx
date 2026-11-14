import { Loader, Wifi, WifiOff } from "lucide-react";
import { useEffect, useState } from "react";

import { t, type Lang } from "@/i18n";
import { getHealth } from "@/lib/api";
import { cn } from "@/lib/utils";

type Status = "checking" | "connected" | "offline";
const RECHECK_MS = 15000;

/** Small "Connected / Offline" line. Always icon + word + colour together. */
export function BackendStatus({ lang }: { lang: Lang }) {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        const health = await getHealth();
        if (!cancelled) setStatus(health.status === "ok" ? "connected" : "offline");
      } catch {
        // Backend down, slow, or returned something unexpected.
        if (!cancelled) setStatus("offline");
      }
    }
    void check();
    const timer = window.setInterval(check, RECHECK_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const view = {
    checking: { Icon: Loader, key: "checking_connection", style: "bg-muted text-muted-foreground" },
    connected: { Icon: Wifi, key: "connected", style: "bg-ok-soft text-ok" },
    offline: { Icon: WifiOff, key: "offline", style: "bg-danger-soft text-danger" },
  } as const;
  const { Icon, key, style } = view[status];

  return (
    <p
      role="status"
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm leading-snug font-semibold",
        style,
      )}
    >
      <Icon className="size-4 shrink-0" aria-hidden="true" />
      {t(lang, key)}
    </p>
  );
}
