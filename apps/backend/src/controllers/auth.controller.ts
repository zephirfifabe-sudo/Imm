import type { Request, Response } from "express";
import { getCurrentUser, loginUser, registerUser } from "../services/auth/auth.service";

export async function register(req: Request, res: Response) {
  const { email, password, fullName } = req.body;
  const result = await registerUser(email, password, fullName);
  res.status(201).json(result);
}

export async function login(req: Request, res: Response) {
  const { email, password } = req.body;
  const result = await loginUser(email, password);
  res.status(200).json(result);
}

export async function me(req: Request, res: Response) {
  const user = await getCurrentUser(req.user!.id);
  res.status(200).json({ user });
}
