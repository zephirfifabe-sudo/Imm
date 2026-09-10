import { app } from "./app";
import { env } from "./config/env";
import { logger } from "./utils/logger";

app.listen(env.port, () => {
  logger.info(`PréVisite API démarrée sur le port ${env.port} (${env.nodeEnv})`);
});
