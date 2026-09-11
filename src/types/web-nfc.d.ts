/**
 * API Web NFC (expérimentale, Chrome sur Android uniquement à ce jour).
 * Absente des types DOM standards de TypeScript — déclarée ici a minima
 * pour éviter tout `any` côté terminal. Le terminal doit rester utilisable
 * sans cette API (lecteur NFC USB en mode clavier, ou saisie manuelle) —
 * voir `src/app/terminal/page.tsx`.
 */
interface NDEFReadingEvent extends Event {
  readonly serialNumber: string;
}

interface NDEFReader extends EventTarget {
  scan(options?: { signal?: AbortSignal }): Promise<void>;
  onreading: ((this: NDEFReader, event: NDEFReadingEvent) => void) | null;
}

interface Window {
  NDEFReader?: { new (): NDEFReader };
}
