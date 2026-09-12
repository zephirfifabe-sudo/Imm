import { type InputHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/cn";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={cn(
          "w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted transition-colors focus:border-primary focus:outline-2 focus:outline-offset-1 focus:outline-primary",
          className,
        )}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";
