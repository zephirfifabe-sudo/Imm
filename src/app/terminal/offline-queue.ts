import type { TimeEntryType } from "@/types/database";

const QUEUE_STORAGE_KEY = "klock_terminal_offline_queue";

// Dupliqué depuis IdentificationMethod (lib/timeclock/identification-providers,
// un module "server-only") plutôt qu'importé: ce fichier est du code client,
// et server-only casse le build s'il est importé côté client.
export type QueuedClockEvent = {
  eventId: string;
  employeeId: string;
  type: TimeEntryType;
  method: "PIN" | "QR" | "NFC";
  occurredAt: string;
};

/**
 * File d'attente hors-ligne du terminal, dans localStorage. Volumes
 * attendus: quelques pointages en attente au plus (une coupure réseau de
 * quelques minutes à quelques heures pour une poignée d'employés) — pas
 * besoin d'IndexedDB pour ça.
 */
export function readQueue(): QueuedClockEvent[] {
  try {
    const raw = window.localStorage.getItem(QUEUE_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeQueue(queue: QueuedClockEvent[]): void {
  window.localStorage.setItem(QUEUE_STORAGE_KEY, JSON.stringify(queue));
  notifyListeners();
}

// Permet à l'UI de lire la longueur de la file via useSyncExternalStore
// (la file change uniquement par nos propres appels ci-dessous, jamais par
// un événement navigateur — un simple pub/sub interne suffit).
const listeners = new Set<() => void>();

function notifyListeners(): void {
  for (const listener of listeners) listener();
}

export function subscribeQueue(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function enqueue(event: QueuedClockEvent): void {
  const queue = readQueue();
  queue.push(event);
  writeQueue(queue);
}

export function removeFromQueue(eventId: string): void {
  writeQueue(readQueue().filter((e) => e.eventId !== eventId));
}
