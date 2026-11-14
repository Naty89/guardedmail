import { toWesternDigits } from "@/lib/format";

/**
 * Wrap a number, amount or date in <bdi> so it keeps its own left-to-right
 * order inside right-to-left text, and always show Western digits 0-9.
 * Usage: <Num>{formatCents(8412)}</Num>
 */
export function Num({ children, className }: { children: string | number; className?: string }) {
  return (
    <bdi dir="ltr" className={className}>
      {toWesternDigits(String(children))}
    </bdi>
  );
}
