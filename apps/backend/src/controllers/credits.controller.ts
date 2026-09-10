import type { Request, Response } from "express";
import { CREDIT_PACKS } from "@previsite/shared";
import { getCreditSummary } from "../services/credits/credits.service";

export async function getMyCredits(req: Request, res: Response) {
  const summary = await getCreditSummary(req.user!.id);
  res.status(200).json(summary);
}

export async function listCreditPacks(_req: Request, res: Response) {
  res.status(200).json({ packs: CREDIT_PACKS });
}
