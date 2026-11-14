import { ArrowLeft, Construction } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardDescription } from "@/components/ui/card";
import { t, type Lang } from "@/i18n";

/**
 * Shared body for screens that are not built yet. When you build a screen,
 * stop using this component in that screen's file.
 */
export function PlaceholderScreen({
  lang,
  title,
  milestone,
  onBack,
  children,
}: {
  lang: Lang;
  title: string;
  /** Developer note, e.g. "M4". Shown in English on purpose. */
  milestone: string;
  onBack: () => void;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <h1 className="text-2xl leading-snug font-bold">{title}</h1>
        {children}
        <CardDescription className="flex items-start gap-2">
          <Construction className="mt-1 size-5 shrink-0" aria-hidden="true" />
          <span>
            {t(lang, "coming_soon")}{" "}
            <bdi lang="en" dir="ltr" className="font-mono text-sm">
              [placeholder, {milestone}]
            </bdi>
          </span>
        </CardDescription>
      </Card>
      <Button variant="outline" onClick={onBack}>
        <ArrowLeft className="rtl:rotate-180" aria-hidden="true" />
        {t(lang, "back")}
      </Button>
    </div>
  );
}
