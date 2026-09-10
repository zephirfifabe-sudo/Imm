import { PrismaClient } from "@prisma/client";

/** Instance unique de Prisma Client, partagée par toute l'app (évite l'épuisement des connexions). */
export const prisma = new PrismaClient();
