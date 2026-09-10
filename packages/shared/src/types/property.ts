/** Types de bien pris en charge par le MVP (marché belge, priorité Wallonie). */
export type PropertyType = "maison" | "appartement" | "studio" | "terrain";

/** Classes PEB (Belgique) et DPE (France) — traitées sur la même échelle A→G. */
export type EnergyClass = "A" | "B" | "C" | "D" | "E" | "F" | "G";

export type EnergyStandard = "PEB" | "DPE";

export interface EnergyRating {
  standard: EnergyStandard;
  energyClass: EnergyClass;
}

export interface Location {
  /** Nom de la commune (ex. "Namur", "Liège"). */
  commune: string;
  /** Code postal belge (4 chiffres) ou français (5 chiffres). */
  postalCode: string;
  /** Code pays ISO 3166-1 alpha-2. Le MVP cible "BE" en priorité. */
  countryCode: "BE" | "FR";
}
