/* shadcn/ui Button (hand-added), with sizes raised to 48px+ tap targets. */
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg text-center font-semibold leading-snug transition-colors disabled:cursor-not-allowed disabled:opacity-60 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/70",
        outline:
          "border-2 border-control-border bg-card text-foreground hover:bg-secondary",
        ghost: "text-foreground hover:bg-muted",
        destructive: "bg-danger text-white hover:bg-danger/90",
      },
      size: {
        // min-h-12 = 3rem = 54px at the 18px base, above the 48px minimum.
        default: "min-h-12 px-4 py-2 text-base [&_svg]:size-5",
        lg: "min-h-18 px-6 py-3 text-xl [&_svg]:size-7",
        icon: "size-12 [&_svg]:size-6",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

type ButtonProps = ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean };

function Button({ className, variant, size, asChild = false, type, ...props }: ButtonProps) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      data-slot="button"
      type={asChild ? undefined : (type ?? "button")}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}

export { Button, buttonVariants };
