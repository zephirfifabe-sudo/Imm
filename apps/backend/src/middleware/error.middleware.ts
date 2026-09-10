import type { NextFunction, Request, Response } from "express";
import { ZodError, type ZodIssue } from "zod";
import { logger } from "../utils/logger";

/**
 * Détecte une ZodError par duck-typing en plus de `instanceof` : le schéma
 * qui lève l'erreur peut provenir de `@previsite/shared` (compilé
 * séparément), et selon l'outil qui charge les modules (bundler de test,
 * runtime différent...), on peut se retrouver avec deux instances de la
 * classe `zod` chargées séparément — `instanceof` échouerait alors à tort.
 */
function isZodError(err: unknown): err is ZodError {
  if (err instanceof ZodError) return true;
  return (
    typeof err === "object" &&
    err !== null &&
    "issues" in err &&
    Array.isArray((err as { issues: unknown }).issues)
  );
}

export class ApiError extends Error {
  constructor(
    public statusCode: number,
    message: string,
  ) {
    super(message);
  }
}

export function notFoundHandler(_req: Request, res: Response) {
  res.status(404).json({ error: "Ressource introuvable." });
}

export function errorHandler(
  err: unknown,
  _req: Request,
  res: Response,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  _next: NextFunction,
) {
  if (isZodError(err)) {
    res.status(400).json({
      error: "Données invalides.",
      details: (err.issues as ZodIssue[]).map((issue) => ({
        path: issue.path.join("."),
        message: issue.message,
      })),
    });
    return;
  }

  if (err instanceof ApiError) {
    res.status(err.statusCode).json({ error: err.message });
    return;
  }

  logger.error("Erreur interne non gérée", { err });
  res.status(500).json({ error: "Erreur interne du serveur." });
}
