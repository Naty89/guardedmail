import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Text that screen readers announce when it changes, without stealing focus.
 * Used for step text such as "Reading your letter…". Keep this element
 * mounted and change only its children, otherwise nothing is announced.
 */
export function LiveRegion({
  children,
  className,
  visuallyHidden = false,
}: {
  children: ReactNode;
  className?: string;
  visuallyHidden?: boolean;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      className={cn(visuallyHidden && "sr-only", className)}
    >
      {children}
    </div>
  );
}
