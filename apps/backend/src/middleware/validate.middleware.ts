import type { NextFunction, Request, Response } from "express";
import type { ZodSchema } from "zod";

/** Valide `req.body` contre un schéma zod et remplace le body par la version parsée/typée. */
export function validateBody(schema: ZodSchema) {
  return (req: Request, _res: Response, next: NextFunction) => {
    req.body = schema.parse(req.body);
    next();
  };
}
