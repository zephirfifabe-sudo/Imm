import type { Request, Response } from "express";
import { z } from "zod";
import { energyClassSchema, propertyTypeSchema } from "@previsite/shared";
import {
  createAnalysis,
  getAnalysisForUser,
  listAnalysesForUser,
} from "../services/analyses/analyses.service";
import { ApiError } from "../middleware/error.middleware";

/**
 * Le formulaire mobile envoie les champs en multipart/form-data (aux côtés
 * des photos) : tout arrive en `req.body` sous forme de chaînes, d'où le
 * `coerce` — contrairement à `analysisInputSchema` (shared) qui valide un
 * payload JSON déjà typé côté formulaire mobile avant l'envoi.
 */
const createAnalysisFormSchema = z.object({
  propertyType: propertyTypeSchema,
  askingPrice: z.coerce.number().positive(),
  livingAreaM2: z.coerce.number().positive().optional(),
  commune: z.string().min(2),
  postalCode: z.string().regex(/^\d{4,5}$/),
  countryCode: z.enum(["BE", "FR"]),
  energyStandard: z.enum(["PEB", "DPE"]).optional(),
  energyClass: energyClassSchema.optional(),
});

export async function postAnalysis(req: Request, res: Response) {
  const parsed = createAnalysisFormSchema.parse(req.body);
  const files = (req.files as Express.Multer.File[] | undefined) ?? [];

  const analysis = await createAnalysis({
    userId: req.user!.id,
    files,
    input: {
      propertyType: parsed.propertyType,
      askingPrice: parsed.askingPrice,
      livingAreaM2: parsed.livingAreaM2,
      location: {
        commune: parsed.commune,
        postalCode: parsed.postalCode,
        countryCode: parsed.countryCode,
      },
      energyRating:
        parsed.energyStandard && parsed.energyClass
          ? { standard: parsed.energyStandard, energyClass: parsed.energyClass }
          : undefined,
      photoUrls: [],
    },
  });

  res.status(201).json({ analysis });
}

export async function getHistory(req: Request, res: Response) {
  const analyses = await listAnalysesForUser(req.user!.id);
  res.status(200).json({ analyses });
}

export async function getAnalysis(req: Request, res: Response) {
  const { id } = req.params;
  if (!id) {
    throw new ApiError(400, "Identifiant d'analyse manquant.");
  }
  const analysis = await getAnalysisForUser(req.user!.id, id);
  res.status(200).json({ analysis });
}
