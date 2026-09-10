import { Router } from "express";
import { getMyCredits, listCreditPacks } from "../controllers/credits.controller";
import { requireAuth } from "../middleware/auth.middleware";
import { asyncHandler } from "../utils/async-handler";

export const creditsRouter = Router();

creditsRouter.get("/me", requireAuth, asyncHandler(getMyCredits));
creditsRouter.get("/packs", asyncHandler(listCreditPacks));
