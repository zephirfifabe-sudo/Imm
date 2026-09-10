import bcrypt from "bcryptjs";
import { prisma } from "./prisma";
import { logger } from "../utils/logger";

async function main() {
  const email = "demo@previsite.be";
  const existing = await prisma.user.findUnique({ where: { email } });
  if (existing) {
    logger.info("Utilisateur de démo déjà présent, seed ignoré.");
    return;
  }

  const passwordHash = await bcrypt.hash("previsite-demo", 12);
  await prisma.user.create({
    data: { email, passwordHash, fullName: "Utilisateur Démo" },
  });
  logger.info(`Utilisateur de démo créé : ${email} / previsite-demo`);
}

main()
  .catch((err) => {
    logger.error("Échec du seed", { err });
    process.exitCode = 1;
  })
  .finally(() => prisma.$disconnect());
