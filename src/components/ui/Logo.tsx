import { useId, type SVGProps } from "react";
import { cn } from "@/lib/cn";

/**
 * Marque KLOCK: un cadran d'horloge minimaliste (deux aiguilles) sur un
 * badge arrondi en dégradé violet — pas d'image externe, un SVG vectoriel
 * pour rester net à toutes les tailles (favicon comme grand format kiosque).
 */
export function LogoMark({ className, ...props }: SVGProps<SVGSVGElement>) {
  const gradientId = useId();

  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden="true" {...props}>
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#8b5cf6" />
          <stop offset="100%" stopColor="#6d28d9" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="10" fill={`url(#${gradientId})`} />
      <circle cx="20" cy="20" r="11" fill="none" stroke="white" strokeWidth="2" />
      <path
        d="M20 13.5v6.8l4.8 2.7"
        fill="none"
        stroke="white"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Logo({
  className,
  markClassName,
  textClassName,
}: {
  className?: string;
  markClassName?: string;
  textClassName?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <LogoMark className={cn("h-7 w-7 shrink-0", markClassName)} />
      <span
        className={cn(
          "text-lg font-bold tracking-tight text-foreground",
          textClassName,
        )}
      >
        KLOCK
      </span>
    </span>
  );
}
