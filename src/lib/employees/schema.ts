import { z } from "zod";

/** PIN à 4 chiffres, saisi au terminal pour s'identifier. */
export const PIN_REGEX = /^\d{4}$/;

export const employeeFormSchema = z.object({
  firstName: z.string().trim().min(1).max(100),
  lastName: z.string().trim().min(1).max(100),
  email: z
    .string()
    .trim()
    .email()
    .optional()
    .or(z.literal(""))
    .transform((v) => v || undefined),
  internalCode: z.string().trim().min(1).max(50),
  jobTitle: z
    .string()
    .trim()
    .max(100)
    .optional()
    .or(z.literal(""))
    .transform((v) => v || undefined),
  siteId: z
    .string()
    .uuid()
    .optional()
    .or(z.literal(""))
    .transform((v) => v || undefined),
  pin: z
    .string()
    .regex(PIN_REGEX, "Le PIN doit contenir exactement 4 chiffres.")
    .optional()
    .or(z.literal(""))
    .transform((v) => v || undefined),
  nfcToken: z
    .string()
    .trim()
    .max(200)
    .optional()
    .or(z.literal(""))
    .transform((v) => v || undefined),
});

export type EmployeeFormInput = z.infer<typeof employeeFormSchema>;
