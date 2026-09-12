import { type ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    "bg-gradient-to-br from-primary-light to-primary-dark text-primary-foreground shadow-[0_6px_16px_-4px_rgba(5,150,105,0.45)] hover:shadow-[0_8px_20px_-4px_rgba(5,150,105,0.55)] hover:brightness-105 active:brightness-95",
  secondary: "bg-surface text-foreground border border-border hover:bg-border/40",
  danger: "bg-danger text-white hover:opacity-90",
  ghost: "bg-transparent text-foreground hover:bg-surface",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center rounded-xl px-4 py-2.5 text-sm font-semibold transition-all disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none disabled:brightness-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
          VARIANT_CLASSES[variant],
          className,
        )}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";
