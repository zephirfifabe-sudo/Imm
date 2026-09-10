import {
  computeScoring,
  type AnalysisInput,
  type AnalysisRecord,
  type EnergyClass,
} from "@previsite/shared";
import { prisma } from "../../db/prisma";
import { ApiError } from "../../middleware/error.middleware";
import { consumeAnalysisEntitlement } from "../credits/credits.service";
import { processUploadedPhotos } from "../photos/photo-processing";
import { analyzePropertyPhotos } from "../vision/vision.service";
import { generateSynthesis } from "../synthesis/synthesis.service";

export interface CreateAnalysisParams {
  userId: string;
  input: AnalysisInput;
  files: Express.Multer.File[];
}

function toAnalysisRecord(row: {
  id: string;
  createdAt: Date;
  propertyType: string;
  askingPrice: number;
  livingAreaM2: number | null;
  commune: string;
  postalCode: string;
  countryCode: string;
  energyStandard: string | null;
  energyClass: string | null;
  photoUrls: string;
  visionResult: string;
  scoringResult: string;
  synthesis: string;
}): AnalysisRecord {
  return {
    id: row.id,
    createdAt: row.createdAt.toISOString(),
    input: {
      propertyType: row.propertyType as AnalysisInput["propertyType"],
      askingPrice: row.askingPrice,
      livingAreaM2: row.livingAreaM2 ?? undefined,
      location: {
        commune: row.commune,
        postalCode: row.postalCode,
        countryCode: row.countryCode as AnalysisInput["location"]["countryCode"],
      },
      energyRating:
        row.energyStandard && row.energyClass
          ? {
              standard: row.energyStandard as "PEB" | "DPE",
              energyClass: row.energyClass as EnergyClass,
            }
          : undefined,
      photoUrls: JSON.parse(row.photoUrls),
    },
    vision: JSON.parse(row.visionResult),
    scoring: JSON.parse(row.scoringResult),
    synthesis: JSON.parse(row.synthesis),
  };
}

/**
 * Orchestre une analyse complète : consomme un droit d'analyse, traite les
 * photos, appelle l'IA vision, calcule le score avec les règles explicites
 * (packages/shared/scoring — jamais laissé à l'IA), puis génère la
 * synthèse finale à partir du résultat déjà calculé, et persiste le tout.
 */
export async function createAnalysis(params: CreateAnalysisParams): Promise<AnalysisRecord> {
  const { userId, input, files } = params;

  if (files.length === 0) {
    throw new ApiError(400, "Ajoute au moins une photo du bien.");
  }

  // Consommé avant l'appel IA (payant) pour ne jamais facturer un appel non couvert.
  await consumeAnalysisEntitlement(userId);

  const processedPhotos = await processUploadedPhotos(files);
  const vision = await analyzePropertyPhotos(processedPhotos.map((p) => p.forVision));

  const scoring = computeScoring({
    propertyType: input.propertyType,
    askingPrice: input.askingPrice,
    livingAreaM2: input.livingAreaM2,
    postalCode: input.location.postalCode,
    commune: input.location.commune,
    energyClass: input.energyRating?.energyClass,
    vision,
  });

  const synthesis = await generateSynthesis(input, vision, scoring);

  const created = await prisma.analysis.create({
    data: {
      userId,
      propertyType: input.propertyType,
      askingPrice: input.askingPrice,
      livingAreaM2: input.livingAreaM2,
      commune: input.location.commune,
      postalCode: input.location.postalCode,
      countryCode: input.location.countryCode,
      energyStandard: input.energyRating?.standard,
      energyClass: input.energyRating?.energyClass,
      photoUrls: JSON.stringify(processedPhotos.map((p) => p.url)),
      visionResult: JSON.stringify(vision),
      scoringResult: JSON.stringify(scoring),
      score: scoring.score,
      verdict: scoring.verdict,
      synthesis: JSON.stringify(synthesis),
    },
  });

  return toAnalysisRecord(created);
}

export async function listAnalysesForUser(userId: string): Promise<AnalysisRecord[]> {
  const rows = await prisma.analysis.findMany({
    where: { userId },
    orderBy: { createdAt: "desc" },
  });
  return rows.map(toAnalysisRecord);
}

export async function getAnalysisForUser(userId: string, analysisId: string): Promise<AnalysisRecord> {
  const row = await prisma.analysis.findFirst({ where: { id: analysisId, userId } });
  if (!row) {
    throw new ApiError(404, "Analyse introuvable.");
  }
  return toAnalysisRecord(row);
}
