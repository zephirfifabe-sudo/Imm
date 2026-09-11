"use client";

import { useState, useSyncExternalStore } from "react";
import {
  activateTerminalAction,
  identifyEmployeeAction,
  recordClockAction,
} from "./actions";
import type { TimeEntryType } from "@/types/database";

const STORAGE_KEY = "klock_terminal_token";

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

type Screen =
  | { name: "home" }
  | { name: "pin" }
  | { name: "qr" }
  | {
      name: "identified";
      employeeId: string;
      firstName: string;
      validActions: TimeEntryType[];
      method: "PIN" | "QR";
    }
  | { name: "success"; firstName: string; type: TimeEntryType; occurredAt: string };

export default function TerminalPage() {
  const token = useSyncExternalStore(subscribeNever, readToken, readServerToken);
  const [screen, setScreen] = useState<Screen>({ name: "home" });
  const [pin, setPin] = useState("");
  const [qrValue, setQrValue] = useState("");
  const [activationCode, setActivationCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);

  function resetToHome() {
    setScreen({ name: "home" });
    setPin("");
    setQrValue("");
    setError(null);
  }

  async function handleActivate() {
    setIsPending(true);
    setError(null);
    const result = await activateTerminalAction(activationCode);
    setIsPending(false);

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
  }

  async function handleIdentify(method: "PIN" | "QR", value: string) {
    if (!token) return;
    setIsPending(true);
    setError(null);
    const result = await identifyEmployeeAction(token, method, value);
    setIsPending(false);

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
  }

  async function handleClock(type: TimeEntryType) {
    if (!token || screen.name !== "identified") return;
    setIsPending(true);
    setError(null);
    const eventId = crypto.randomUUID();
    const result = await recordClockAction(
      token,
      screen.employeeId,
      type,
      screen.method,
      eventId,
    );
    setIsPending(false);

    if (!result.ok) {
      setError(
        result.error === "invalid_transition"
          ? "Cette action n'est plus valide, merci de recommencer."
          : "Une erreur est survenue.",
      );
      return;
    }

    setScreen({
      name: "success",
      firstName: screen.firstName,
      type: result.type,
      occurredAt: result.occurredAt,
    });
    setTimeout(resetToHome, 3000);
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-surface px-6 py-10 text-center">
      <h1 className="mb-10 text-4xl font-bold tracking-tight text-primary">KLOCK</h1>

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
    </main>
  );
}
