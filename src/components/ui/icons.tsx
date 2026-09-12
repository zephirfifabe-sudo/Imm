import type { SVGProps } from "react";

/**
 * Icônes du terminal, dessinées à la main (pas de dépendance externe pour
 * un si petit ensemble — évite d'ajouter une librairie entière pour une
 * dizaine de pictogrammes). Style cohérent: trait fin, coins arrondis.
 */

function Svg(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    />
  );
}

export function PinIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Svg {...props}>
      <rect x="4" y="4" width="4.2" height="4.2" rx="1" />
      <rect x="9.9" y="4" width="4.2" height="4.2" rx="1" />
      <rect x="15.8" y="4" width="4.2" height="4.2" rx="1" />
      <rect x="4" y="9.9" width="4.2" height="4.2" rx="1" />
      <rect x="9.9" y="9.9" width="4.2" height="4.2" rx="1" />
      <rect x="15.8" y="9.9" width="4.2" height="4.2" rx="1" />
      <rect x="4" y="15.8" width="4.2" height="4.2" rx="1" />
      <rect x="9.9" y="15.8" width="4.2" height="4.2" rx="1" />
      <circle cx="17.9" cy="17.9" r="2.1" />
    </Svg>
  );
}

export function QrIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Svg {...props}>
      <rect x="3.5" y="3.5" width="6.5" height="6.5" rx="1.2" />
      <rect x="14" y="3.5" width="6.5" height="6.5" rx="1.2" />
      <rect x="3.5" y="14" width="6.5" height="6.5" rx="1.2" />
      <path d="M14 14h3v3h-3zM19.5 14v3M14 19.5h3" />
    </Svg>
  );
}

export function NfcIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Svg {...props}>
      <path d="M6 16.5C8.5 14.5 8.5 9.5 6 7.5" />
      <path d="M10 19C14 15.5 14 8.5 10 5" />
      <path d="M14 21c5.5-4.5 5.5-13.5 0-18" />
    </Svg>
  );
}

export function WarningIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Svg {...props}>
      <path d="M12 3.5 21 19.5H3L12 3.5Z" />
      <path d="M12 9.5v4.2M12 16.7h.01" />
    </Svg>
  );
}

export function CheckCircleIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M8.3 12.3l2.6 2.6 4.8-5.4" />
    </Svg>
  );
}

export function ClockPendingIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3.2 2" />
    </Svg>
  );
}

export function BackspaceIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Svg {...props}>
      <path d="M9 5h10.5a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H9l-6-7 6-7Z" />
      <path d="M13 10.2l4.2 4.2M17.2 10.2 13 14.4" />
    </Svg>
  );
}

export function LockIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Svg {...props}>
      <rect x="5" y="10.5" width="14" height="9.5" rx="2" />
      <path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" />
    </Svg>
  );
}

export function WifiOffIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Svg {...props}>
      <path d="M2.5 2.5l19 19" />
      <path d="M8.5 16.5a5 5 0 0 1 6.2-.4M5.2 13a10 10 0 0 1 3-2.1M12 20h.01" />
      <path d="M18.8 13a10 10 0 0 0-2.6-1.9M16 8.5a13.5 13.5 0 0 1 3.9 2.6M4.1 8.5A13.4 13.4 0 0 1 12 5.5c1.9 0 3.7.4 5.3 1.1" />
    </Svg>
  );
}
