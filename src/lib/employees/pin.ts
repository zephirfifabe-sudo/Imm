import "server-only";
import bcrypt from "bcryptjs";

const SALT_ROUNDS = 10;

export function hashPin(pin: string): Promise<string> {
  return bcrypt.hash(pin, SALT_ROUNDS);
}

export function pinMatchesHash(pin: string, hash: string): Promise<boolean> {
  return bcrypt.compare(pin, hash);
}
