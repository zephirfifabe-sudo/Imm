import { Router } from "express";
import { getAnalysis, getHistory, postAnalysis } from "../controllers/analyses.controller";
import { requireAuth } from "../middleware/auth.middleware";
import { photoUpload } from "../middleware/upload.middleware";
import { asyncHandler } from "../utils/async-handler";

export const analysesRouter = Router();

analysesRouter.use(requireAuth);
analysesRouter.post("/", photoUpload.array("photos", 10), asyncHandler(postAnalysis));
analysesRouter.get("/", asyncHandler(getHistory));
analysesRouter.get("/:id", asyncHandler(getAnalysis));
