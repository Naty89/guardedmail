import { Bug } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { t, type Lang } from "@/i18n";
import { SCREENS, type Screen } from "@/lib/screens";

/**
 * Drawer shown only with ?debug=1. EMPTY PLACEHOLDER: milestone M7 fills it.
 * It is always English (judges read it), so it sets lang/dir itself.
 * Until M7 it only offers "jump to screen" so teammates can reach the
 * placeholder screens while they build them.
 */
export function JudgePanel({
  lang,
  screen,
  go,
}: {
  lang: Lang;
  screen: Screen;
  go: (screen: Screen) => void;
}) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          lang="en"
          dir="ltr"
          className="fixed end-3 bottom-3 z-20 rounded-full shadow-md"
        >
          <Bug aria-hidden="true" />
          {t("en", "judge_panel")}
        </Button>
      </DialogTrigger>
      <DialogContent lang="en" dir="ltr" closeLabel={t("en", "close")}>
        <DialogTitle>{t("en", "judge_panel")}</DialogTitle>
        <DialogDescription>{t("en", "judge_panel_empty")}</DialogDescription>

        {/* TODO(M7): trace of reader / scam / policy steps for this letter. */}

        <section aria-labelledby="jump-heading" className="flex flex-col gap-2">
          <h3 id="jump-heading" className="text-sm font-semibold text-muted-foreground">
            {t("en", "jump_to_screen")} (UI language: {lang})
          </h3>
          <div className="grid grid-cols-2 gap-2">
            {SCREENS.map((name) => (
              <DialogClose asChild key={name}>
                <Button
                  variant={name === screen ? "default" : "outline"}
                  aria-pressed={name === screen}
                  onClick={() => go(name)}
                >
                  {name}
                </Button>
              </DialogClose>
            ))}
          </div>
        </section>
      </DialogContent>
    </Dialog>
  );
}
