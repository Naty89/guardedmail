/* shadcn/ui Card (hand-added, trimmed to the parts we use). Hairline edge, soft shadow. */
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

function Card({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="card"
      className={cn(
        "flex flex-col gap-4 rounded-2xl border border-hairline bg-surface p-5 text-card-foreground shadow-card",
        className,
      )}
      {...props}
    />
  );
}

function CardTitle({ className, ...props }: ComponentProps<"h2">) {
  return (
    <h2
      data-slot="card-title"
      className={cn("text-xl leading-snug font-semibold", className)}
      {...props}
    />
  );
}

function CardDescription({ className, ...props }: ComponentProps<"p">) {
  return (
    <p data-slot="card-description" className={cn("text-muted-foreground", className)} {...props} />
  );
}

export { Card, CardDescription, CardTitle };
