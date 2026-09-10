/**
 * Palette sobre et professionnelle : bleu profond / anthracite en base,
 * accent vert (bonne affaire) / orange (à creuser) / rouge (à éviter)
 * réservés aux scores — jamais utilisés comme couleurs décoratives.
 */
export const colors = {
  background: "#F5F7FA",
  surface: "#FFFFFF",
  surfaceMuted: "#EDF1F6",
  border: "#DDE3EC",

  primary: "#12233F",
  primaryDark: "#0A1526",
  primaryMuted: "#2C4468",

  textPrimary: "#131A24",
  textSecondary: "#4B5768",
  textOnPrimary: "#FFFFFF",
  textOnPrimaryMuted: "#C7D2E3",

  success: "#1E8A5F",
  successMuted: "#E4F4EC",
  warning: "#C97A1F",
  warningMuted: "#FBF0E1",
  danger: "#B93B3B",
  dangerMuted: "#FAE7E7",

  overlay: "rgba(10, 21, 38, 0.55)",
} as const;
