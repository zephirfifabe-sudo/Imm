import { z } from "zod";

export const CONTRACT_TYPES = ["CDI", "CDD", "Intérim", "Flexi-job", "Étudiant"] as const;

/**
 * Champs de planification d'un employé (heures contractuelles, nuits...).
 * Tous optionnels côté formulaire: un employé peut exister sans jamais être
 * inclus dans le planificateur, auquel cas aucune ligne n'est créée dans
 * `employee_scheduling_profiles`.
 */
export const employeeSchedulingProfileSchema = z
  .object({
    contractHoursPerWeek: z.coerce.number().min(1).max(60).optional(),
    contractType: z.enum(CONTRACT_TYPES).optional(),
    dayOnly: z.coerce.boolean().optional().default(false),
    nightOnly: z.coerce.boolean().optional().default(false),
    minNightsPerPeriod: z.coerce.number().int().min(0).max(28).optional().default(0),
    maxNightsPerPeriod: z.coerce.number().int().min(0).max(28).optional().default(8),
  })
  .refine((data) => !(data.dayOnly && data.nightOnly), {
    message: "Un employé ne peut pas être à la fois journée uniquement et nuit uniquement.",
    path: ["dayOnly"],
  })
  .refine((data) => data.minNightsPerPeriod <= data.maxNightsPerPeriod, {
    message: "Le minimum de nuits ne peut pas dépasser le maximum.",
    path: ["minNightsPerPeriod"],
  });

export type EmployeeSchedulingProfileInput = z.infer<typeof employeeSchedulingProfileSchema>;
