import type { WorkExtent } from "../types/analysis";

/** Points retirés du score sur 10 selon l'étendue des travaux visibles en photo. */
export const WORK_EXTENT_PENALTY: Record<WorkExtent, number> = {
  "léger": 0.5,
  "modéré": 2,
  "important": 4,
};
