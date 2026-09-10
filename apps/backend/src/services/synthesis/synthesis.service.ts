import Anthropic from "@anthropic-ai/sdk";
import {
  synthesisResultSchema,
  type AnalysisInput,
  type ScoringResult,
  type SynthesisResult,
  type VisionAnalysisResult,
} from "@previsite/shared";
import { env } from "../../config/env";
import { ApiError } from "../../middleware/error.middleware";
import { buildSynthesisUserPrompt, SYNTHESIS_SYSTEM_PROMPT, WRITE_SYNTHESIS_TOOL } from "./synthesis.prompt";

const anthropic = new Anthropic({ apiKey: env.anthropicApiKey });

/**
 * Rédige la synthèse finale à partir des données DÉJÀ calculées par le
 * moteur de scoring (packages/shared/scoring). Le LLM ne reçoit jamais les
 * photos ici et ne décide jamais du score : il explique un résultat qui lui
 * est donné.
 */
export async function generateSynthesis(
  input: AnalysisInput,
  vision: VisionAnalysisResult,
  scoring: ScoringResult,
): Promise<SynthesisResult> {
  const response = await anthropic.messages.create({
    model: env.anthropicSynthesisModel,
    max_tokens: 1000,
    system: SYNTHESIS_SYSTEM_PROMPT,
    tools: [WRITE_SYNTHESIS_TOOL],
    tool_choice: { type: "tool", name: WRITE_SYNTHESIS_TOOL.name },
    messages: [{ role: "user", content: buildSynthesisUserPrompt(input, vision, scoring) }],
  });

  const toolUse = response.content.find((block) => block.type === "tool_use");
  if (!toolUse || toolUse.type !== "tool_use") {
    throw new ApiError(502, "La synthèse n'a pas pu être générée.");
  }

  const parseResult = synthesisResultSchema.safeParse(toolUse.input);
  if (!parseResult.success) {
    throw new ApiError(502, "Réponse de synthèse invalide.");
  }

  return parseResult.data;
}
