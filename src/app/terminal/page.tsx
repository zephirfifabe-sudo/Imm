"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  activateTerminalAction,
  identifyEmployeeAction,
  recordClockAction,
} from "./actions";
import {
  readQueue,
  enqueue,
  removeFromQueue,
  subscribeQueue,
  type QueuedClockEvent,
} from "./offline-queue";
import type { TimeEntryType } from "@/types/database";

const STORAGE_KEY = "klock_terminal_token";
const SYNC_RETRY_INTERVAL_MS = 20000;

// Pas de synchronisation multi-onglets nécessaire pour une tablette dédiée:
// on ne s'abonne à aucun événement, on relit juste localStorage à chaque
// rendu (déclenché nous-mêmes après writeToken()). useSyncExternalStore
// gère proprement le rendu serveur (aucun localStorage) sans effet ni
// setState dans un effet.
function subscribeNever() {
  return () => {};
}
function readToken() {
  return window.localStorage.getItem(STORAGE_KEY);
}
function readServerToken() {
  return null;
}

// navigator.onLine est l'exemple canonique de useSyncExternalStore: une
// valeur externe qui change via des événements ('online'/'offline'), pas
// via React. Évite un effet qui ferait setState de façon synchrone.
function subscribeOnlineStatus(callback: () => void) {
  window.addEventListener("online", callback);
  window.addEventListener("offline", callback);
  return () => {
    window.removeEventListener("online", callback);
    window.removeEventListener("offline", callback);
  };
}
function readOnlineStatus() {
  return navigator.onLine;
}
function readServerOnlineStatus() {
  return true;
}

function readQueueLength() {
  return readQueue().length;
}
function readServerQueueLength() {
  return 0;
}

const ACTION_LABELS: Record<TimeEntryType, string> = {
  CLOCK_IN: "ARRIVÉE",
  CLOCK_OUT: "DÉPART",
  BREAK_START: "DÉBUT DE PAUSE",
  BREAK_END: "FIN DE PAUSE",
};

const CONFIRM_LABELS: Record<TimeEntryType, string> = {
  CLOCK_IN: "Arrivée enregistrée",
  CLOCK_OUT: "Départ enregistré",
  BREAK_START: "Pause commencée",
  BREAK_END: "Pause terminée",
};

type IdentificationMethod = "PIN" | "QR" | "NFC";

type Screen =
  | { name: "home" }
  | { name: "pin" }
  | { name: "qr" }
  | { name: "nfc" }
  | {
      name: "identified";
      employeeId: string;
      firstName: string;
      validActions: TimeEntryType[];
      method: IdentificationMethod;
    }
  | { name: "success"; firstName: string; type: TimeEntryType; occurredAt: string }
  | { name: "queued"; firstName: string; type: TimeEntryType };

export default function TerminalPage() {
  const token = useSyncExternalStore(subscribeNever, readToken, readServerToken);
  const isOnline = useSyncExternalStore(
    subscribeOnlineStatus,
    readOnlineStatus,
    readServerOnlineStatus,
  );
  const [screen, setScreen] = useState<Screen>({ name: "home" });
  const [pin, setPin] = useState("");
  const [qrValue, setQrValue] = useState("");
  const [nfcValue, setNfcValue] = useState("");
  const [nfcScanState, setNfcScanState] = useState<
    "unsupported" | "scanning" | "error"
  >("unsupported");
  const [activationCode, setActivationCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);
  const pendingCount = useSyncExternalStore(
    subscribeQueue,
    readQueueLength,
    readServerQueueLength,
  );
  const isSyncingRef = useRef(false);

  async function flushQueue(currentToken: string) {
    if (isSyncingRef.current) return;
    isSyncingRef.current = true;

    try {
      for (const item of readQueue()) {
        try {
          await recordClockAction(
            currentToken,
            item.employeeId,
            item.type,
            item.method,
            item.eventId,
            item.occurredAt,
          );
        } catch {
          // Toujours hors ligne (ou réseau instable): on arrête ici et on
          // réessaiera au prochain passage, la file reste intacte.
          break;
        }

        // Qu'il s'agisse d'un succès ou d'une erreur métier définitive
        // (transition devenue invalide entre-temps, employé introuvable),
        // l'événement ne doit pas rester bloqué indéfiniment dans la file.
        removeFromQueue(item.eventId);
      }
    } finally {
      isSyncingRef.current = false;
    }
  }

  // Se resynchronise au retour du réseau, au montage (file laissée par une
  // session précédente), et à intervalle régulier par sécurité si
  // l'événement 'online' du navigateur ne se déclenche pas de façon fiable.
  useEffect(() => {
    if (!token || !isOnline) return;
    void flushQueue(token);
    const interval = setInterval(() => void flushQueue(token), SYNC_RETRY_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [token, isOnline]);

  function resetToHome() {
    setScreen({ name: "home" });
    setPin("");
    setQrValue("");
    setNfcValue("");
    setError(null);
  }

  // Tente une lecture NFC native (Web NFC, Chrome sur Android uniquement)
  // pendant que l'écran NFC est affiché. Le lecteur USB en mode clavier et
  // la saisie manuelle restent toujours disponibles via le champ texte —
  // le terminal ne dépend d'aucun matériel précis pour fonctionner.
  useEffect(() => {
    if (screen.name !== "nfc" || !window.NDEFReader) {
      // Sans Web NFC, l'état reste sur sa valeur par défaut ("unsupported"):
      // le champ texte (lecteur USB ou saisie manuelle) fait le travail.
      return;
    }

    const controller = new AbortController();
    const reader = new window.NDEFReader();

    reader
      .scan({ signal: controller.signal })
      .then(() => {
        setNfcScanState("scanning");
        reader.onreading = (event) => {
          if (event.serialNumber) {
            void handleIdentify("NFC", event.serialNumber);
          }
        };
      })
      .catch(() => {
        setNfcScanState("error");
      });

    return () => controller.abort();
    // handleIdentify est recréée à chaque rendu (elle capture pin/qrValue/...);
    // la re-souscrire à chaque fois relancerait le scan NFC inutilement, alors
    // qu'on ne veut redémarrer que lorsqu'on entre réellement sur cet écran.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screen.name]);

  async function handleActivate() {
    setIsPending(true);
    setError(null);
    try {
      const result = await activateTerminalAction(activationCode);
      if (!result.ok) {
        setError(
          result.error === "invalid_code"
            ? "Code d'activation invalide."
            : "Une erreur est survenue.",
        );
        return;
      }
      window.localStorage.setItem(STORAGE_KEY, result.token);
      setActivationCode("");
      resetToHome();
    } catch {
      setError("Hors ligne — l'activation nécessite une connexion.");
    } finally {
      setIsPending(false);
    }
  }

  async function handleIdentify(method: IdentificationMethod, value: string) {
    if (!token) return;
    setIsPending(true);
    setError(null);
    try {
      const result = await identifyEmployeeAction(token, method, value);
      if (!result.ok) {
        setError(
          result.error === "not_found"
            ? "Identification inconnue."
            : result.error === "invalid_terminal"
              ? "Terminal non reconnu. Contactez votre employeur."
              : "Merci de vérifier votre saisie.",
        );
        setPin("");
        return;
      }
      setScreen({
        name: "identified",
        employeeId: result.employeeId,
        firstName: result.firstName,
        validActions: result.validActions,
        method,
      });
    } catch {
      // L'identification a besoin du serveur (les PIN/QR n'ont pas de copie
      // locale sur le terminal): impossible de reconnaître qui pointe hors
      // ligne, seul l'enregistrement du pointage peut être mis en file.
      setError("Hors ligne — l'identification nécessite une connexion.");
      setPin("");
    } finally {
      setIsPending(false);
    }
  }

  async function handleClock(type: TimeEntryType) {
    if (!token || screen.name !== "identified") return;
    const { employeeId, firstName, method } = screen;
    const eventId = crypto.randomUUID();
    const occurredAt = new Date().toISOString();

    setIsPending(true);
    setError(null);
    try {
      const result = await recordClockAction(
        token,
        employeeId,
        type,
        method,
        eventId,
        occurredAt,
      );
      if (!result.ok) {
        setError(
          result.error === "invalid_transition"
            ? "Cette action n'est plus valide, merci de recommencer."
            : "Une erreur est survenue.",
        );
        return;
      }
      setScreen({ name: "success", firstName, type: result.type, occurredAt: result.occurredAt });
      setTimeout(resetToHome, 3000);
    } catch {
      // Coupure réseau au moment du pointage: on conserve l'heure réelle et
      // on met en file, plutôt que de perdre le pointage de l'employé.
      const queued: QueuedClockEvent = { eventId, employeeId, type, method, occurredAt };
      enqueue(queued);
      setScreen({ name: "queued", firstName, type });
      setTimeout(resetToHome, 3000);
    } finally {
      setIsPending(false);
    }
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-surface px-6 py-10 text-center">
      <h1 className="mb-4 text-4xl font-bold tracking-tight text-primary">KLOCK</h1>

      {!isOnline && (
        <p className="mb-4 rounded-lg bg-amber-100 px-4 py-2 text-sm font-medium text-amber-800">
          ⚠ Hors ligne — les pointages seront synchronisés au retour du réseau
        </p>
      )}
      {pendingCount > 0 && (
        <p className="mb-6 text-xs text-muted">
          {pendingCount} pointage{pendingCount > 1 ? "s" : ""} en attente de synchronisation
        </p>
      )}

      {!token && (
        <div className="w-full max-w-sm space-y-4">
          <p className="text-lg text-foreground">Activation du terminal</p>
          <p className="text-sm text-muted">
            Saisissez le code fourni par votre employeur.
          </p>
          <input
            inputMode="numeric"
            maxLength={6}
            value={activationCode}
            onChange={(e) => setActivationCode(e.target.value.replace(/\D/g, ""))}
            className="w-full rounded-xl border border-border bg-background px-4 py-4 text-center text-3xl tracking-[0.5em]"
            placeholder="000000"
          />
          {error && <p className="text-danger">{error}</p>}
          <button
            type="button"
            disabled={isPending || activationCode.length !== 6}
            onClick={handleActivate}
            className="w-full rounded-xl bg-primary px-6 py-4 text-lg font-semibold text-primary-foreground disabled:opacity-50"
          >
            Activer
          </button>
        </div>
      )}

      {token && screen.name === "home" && (
        <div className="w-full max-w-sm space-y-4">
          <p className="text-xl text-foreground">Comment pointer ?</p>
          <button
            type="button"
            onClick={() => setScreen({ name: "pin" })}
            className="w-full rounded-xl bg-primary px-6 py-6 text-2xl font-semibold text-primary-foreground"
          >
            🔢 PIN
          </button>
          <button
            type="button"
            onClick={() => setScreen({ name: "qr" })}
            className="w-full rounded-xl bg-primary px-6 py-6 text-2xl font-semibold text-primary-foreground"
          >
            📷 QR CODE
          </button>
          <button
            type="button"
            onClick={() => setScreen({ name: "nfc" })}
            className="w-full rounded-xl bg-primary px-6 py-6 text-2xl font-semibold text-primary-foreground"
          >
            📶 NFC
          </button>
        </div>
      )}

      {token && screen.name === "pin" && (
        <div className="w-full max-w-sm space-y-4">
          <p className="text-lg text-foreground">Entrez votre code PIN</p>
          <div className="flex justify-center gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className="h-14 w-12 rounded-lg border border-border bg-background text-3xl leading-[3.5rem]"
              >
                {pin[i] ? "•" : ""}
              </div>
            ))}
          </div>
          {error && <p className="text-danger">{error}</p>}
          <div className="grid grid-cols-3 gap-3">
            {["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "⌫"].map(
              (key, i) =>
                key === "" ? (
                  <div key={i} />
                ) : (
                  <button
                    key={i}
                    type="button"
                    disabled={isPending}
                    onClick={() => {
                      setError(null);
                      if (key === "⌫") {
                        setPin((p) => p.slice(0, -1));
                        return;
                      }
                      const next = (pin + key).slice(0, 4);
                      setPin(next);
                      if (next.length === 4) {
                        void handleIdentify("PIN", next);
                      }
                    }}
                    className="rounded-xl border border-border bg-background py-5 text-2xl font-semibold text-foreground disabled:opacity-50"
                  >
                    {key}
                  </button>
                ),
            )}
          </div>
          <button type="button" onClick={resetToHome} className="text-sm text-muted">
            Annuler
          </button>
        </div>
      )}

      {token && screen.name === "qr" && (
        <div className="w-full max-w-sm space-y-4">
          <p className="text-lg text-foreground">Scannez votre badge QR</p>
          <p className="text-xs text-muted">
            Utilisez le lecteur QR de la borne, ou saisissez le code manuellement.
          </p>
          <input
            autoFocus
            value={qrValue}
            onChange={(e) => setQrValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && qrValue.trim()) {
                void handleIdentify("QR", qrValue.trim());
              }
            }}
            className="w-full rounded-xl border border-border bg-background px-4 py-4 text-center text-lg"
            placeholder="Code du badge"
          />
          {error && <p className="text-danger">{error}</p>}
          <button
            type="button"
            disabled={isPending || !qrValue.trim()}
            onClick={() => handleIdentify("QR", qrValue.trim())}
            className="w-full rounded-xl bg-primary px-6 py-4 text-lg font-semibold text-primary-foreground disabled:opacity-50"
          >
            Valider
          </button>
          <button type="button" onClick={resetToHome} className="text-sm text-muted">
            Annuler
          </button>
        </div>
      )}

      {token && screen.name === "nfc" && (
        <div className="w-full max-w-sm space-y-4">
          <p className="text-lg text-foreground">Approchez votre badge NFC</p>
          <p className="text-xs text-muted">
            {nfcScanState === "scanning"
              ? "En attente du badge..."
              : "Utilisez le lecteur NFC de la borne, ou saisissez le code manuellement."}
          </p>
          <input
            autoFocus
            value={nfcValue}
            onChange={(e) => setNfcValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && nfcValue.trim()) {
                void handleIdentify("NFC", nfcValue.trim());
              }
            }}
            className="w-full rounded-xl border border-border bg-background px-4 py-4 text-center text-lg"
            placeholder="Code du badge"
          />
          {error && <p className="text-danger">{error}</p>}
          <button
            type="button"
            disabled={isPending || !nfcValue.trim()}
            onClick={() => handleIdentify("NFC", nfcValue.trim())}
            className="w-full rounded-xl bg-primary px-6 py-4 text-lg font-semibold text-primary-foreground disabled:opacity-50"
          >
            Valider
          </button>
          <button type="button" onClick={resetToHome} className="text-sm text-muted">
            Annuler
          </button>
        </div>
      )}

      {token && screen.name === "identified" && (
        <div className="w-full max-w-sm space-y-4">
          <p className="text-2xl text-foreground">Bonjour {screen.firstName} 👋</p>
          {error && <p className="text-danger">{error}</p>}
          <div className="space-y-3">
            {screen.validActions.map((action) => (
              <button
                key={action}
                type="button"
                disabled={isPending}
                onClick={() => handleClock(action)}
                className="w-full rounded-xl bg-primary px-6 py-6 text-2xl font-semibold text-primary-foreground disabled:opacity-50"
              >
                {ACTION_LABELS[action]}
              </button>
            ))}
          </div>
          <button type="button" onClick={resetToHome} className="text-sm text-muted">
            Annuler
          </button>
        </div>
      )}

      {token && screen.name === "success" && (
        <div className="w-full max-w-sm space-y-3">
          <p className="text-4xl">✓</p>
          <p className="text-xl font-semibold text-foreground">
            {CONFIRM_LABELS[screen.type]}
          </p>
          <p className="text-3xl font-bold text-primary">
            {new Date(screen.occurredAt).toLocaleTimeString("fr-BE", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </p>
          <p className="text-muted">Bonne journée {screen.firstName} !</p>
        </div>
      )}

      {token && screen.name === "queued" && (
        <div className="w-full max-w-sm space-y-3">
          <p className="text-4xl">⏳</p>
          <p className="text-xl font-semibold text-foreground">
            {CONFIRM_LABELS[screen.type]}
          </p>
          <p className="text-sm text-muted">
            Réseau indisponible — ce pointage sera synchronisé automatiquement dès
            que la connexion revient.
          </p>
          <p className="text-muted">Bonne journée {screen.firstName} !</p>
        </div>
      )}
    </main>
  );
}
