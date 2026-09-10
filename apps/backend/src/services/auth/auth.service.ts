import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
import type { User } from "@prisma/client";
import { env } from "../../config/env";
import { prisma } from "../../db/prisma";
import { ApiError } from "../../middleware/error.middleware";

const SALT_ROUNDS = 12;

export interface AuthResult {
  token: string;
  user: PublicUser;
}

export interface PublicUser {
  id: string;
  email: string;
  fullName: string | null;
  creditBalance: number;
  freeAnalysesUsed: number;
}

function toPublicUser(user: User): PublicUser {
  return {
    id: user.id,
    email: user.email,
    fullName: user.fullName,
    creditBalance: user.creditBalance,
    freeAnalysesUsed: user.freeAnalysesUsed,
  };
}

function issueToken(user: User): string {
  return jwt.sign({ sub: user.id, email: user.email }, env.jwtSecret, {
    expiresIn: env.jwtExpiresIn,
  } as jwt.SignOptions);
}

export async function registerUser(
  email: string,
  password: string,
  fullName?: string,
): Promise<AuthResult> {
  const existing = await prisma.user.findUnique({ where: { email } });
  if (existing) {
    throw new ApiError(409, "Un compte existe déjà avec cette adresse email.");
  }

  const passwordHash = await bcrypt.hash(password, SALT_ROUNDS);
  const user = await prisma.user.create({
    data: { email, passwordHash, fullName },
  });

  return { token: issueToken(user), user: toPublicUser(user) };
}

export async function loginUser(email: string, password: string): Promise<AuthResult> {
  const user = await prisma.user.findUnique({ where: { email } });
  if (!user) {
    throw new ApiError(401, "Email ou mot de passe incorrect.");
  }

  const passwordMatches = await bcrypt.compare(password, user.passwordHash);
  if (!passwordMatches) {
    throw new ApiError(401, "Email ou mot de passe incorrect.");
  }

  return { token: issueToken(user), user: toPublicUser(user) };
}

export async function getCurrentUser(userId: string): Promise<PublicUser> {
  const user = await prisma.user.findUnique({ where: { id: userId } });
  if (!user) {
    throw new ApiError(404, "Utilisateur introuvable.");
  }
  return toPublicUser(user);
}
