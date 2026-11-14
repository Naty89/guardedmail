/* shadcn/ui Button (hand-added), restyled. Every size is at least a 48px tap target. */
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl text-center font-semibold leading-snug transition-[background-color,box-shadow,transform] duration-150 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-55 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-[0_1px_0_rgb(255_255_255/0.16)_inset,0_3px_8px_-3px_rgb(29_78_216/0.6)] hover:bg-primary-hover",
        // Sunny yellow with dark ink text. Use on cobalt blocks, or for one hero action.
        accent:
          "bg-accent text-ink shadow-[0_1px_0_rgb(255_255_255/0.4)_inset,0_3px_8px_-3px_rgb(18_27_56/0.45)] hover:brightness-95",
        // Quiet button on a cobalt block.
        light: "text-white hover:bg-white/12",
        secondary: "bg-primary-soft text-primary-ink hover:bg-primary-soft/70",
        outline:
          "border-[1.5px] border-control-border bg-surface text-foreground hover:bg-primary-soft",
        ghost: "text-primary-ink hover:bg-primary-soft",
        destructive: "bg-danger text-white hover:bg-danger/90",
      },
      size: {
        // min-h-12 = 3rem = 54px at the 18px base, above the 48px minimum.
        default: "min-h-12 px-4 py-2 text-base [&_svg]:size-5",
        lg: "min-h-15 px-6 py-3 text-lg [&_svg]:size-6",
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
