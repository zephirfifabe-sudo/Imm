import { Router } from "express";
import { authRouter } from "./auth.routes";
import { analysesRouter } from "./analyses.routes";
import { creditsRouter } from "./credits.routes";
import { paymentsRouter } from "./payments.routes";

export const apiRouter = Router();

apiRouter.use("/auth", authRouter);
apiRouter.use("/analyses", analysesRouter);
apiRouter.use("/credits", creditsRouter);
apiRouter.use("/payments", paymentsRouter);
