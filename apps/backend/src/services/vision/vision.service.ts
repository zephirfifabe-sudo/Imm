import Anthropic from "@anthropic-ai/sdk";
import { visionAnalysisResultSchema, type VisionAnalysisResult } from "@previsite/shared";
import { env } from "../../config/env";
import { ApiError } from "../../middleware/error.middleware";
import {
  buildVisionUserPrompt,
  REPORT_VISUAL_CONDITION_TOOL,
  VISION_SYSTEM_PROMPT,
} from "./vision.prompt";

const anthropic = new Anthropic({ apiKey: env.anthropicApiKey });

export interface PhotoForAnalysis {
  base64: string;
  mimeType: "image/jpeg" | "image/png" | "image/webp";
}

/**
 * Envoie les photos compressées à Claude (vision) et force une réponse
 * structurée via tool use — jamais de texte libre, la cohérence du
 * scoring en dépend (voir docs/scoring-formula.md).
 */
export async function analyzePropertyPhotos(
  photos: PhotoForAnalysis[],
): Promise<VisionAnalysisResult> {
  if (photos.length === 0) {
    throw new ApiError(400, "Au moins une photo est requise pour l'analyse.");
  }

  const response = await anthropic.messages.create({
    model: env.anthropicVisionModel,
    max_tokens: 1500,
    system: VISION_SYSTEM_PROMPT,
    tools: [REPORT_VISUAL_CONDITION_TOOL],
    tool_choice: { type: "tool", name: REPORT_VISUAL_CONDITION_TOOL.name },
    messages: [
      {
        role: "user",
        content: [
          { type: "text", text: buildVisionUserPrompt(photos.length) },
          ...photos.map((photo) => ({
            type: "image" as const,
            source: {
              type: "base64" as const,
              media_type: photo.mimeType,
              data: photo.base64,
            },
          })),
        ],
      },
    ],
  });

  const toolUse = response.content.find((block) => block.type === "tool_use");
  if (!toolUse || toolUse.type !== "tool_use") {
    throw new ApiError(502, "L'analyse photo n'a pas pu produire de résultat structuré.");
  }

  const parseResult = visionAnalysisResultSchema.safeParse(toolUse.input);
  if (!parseResult.success) {
    throw new ApiError(502, "Réponse d'analyse photo invalide ou incomplète.");
  }

  return parseResult.data;
}
