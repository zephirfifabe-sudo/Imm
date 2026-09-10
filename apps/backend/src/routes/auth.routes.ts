import { Router } from "express";
import { loginSchema, registerSchema } from "@previsite/shared";
import { login, me, register } from "../controllers/auth.controller";
import { asyncHandler } from "../utils/async-handler";
import { requireAuth } from "../middleware/auth.middleware";
import { validateBody } from "../middleware/validate.middleware";

export const authRouter = Router();

authRouter.post("/register", validateBody(registerSchema), asyncHandler(register));
authRouter.post("/login", validateBody(loginSchema), asyncHandler(login));
authRouter.get("/me", requireAuth, asyncHandler(me));
