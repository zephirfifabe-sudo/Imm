import { StyleSheet, Text, View } from "react-native";
import type { Verdict } from "@previsite/shared";
import { colors, radii, spacing, typography } from "../theme";

const VERDICT_COLOR: Record<Verdict, string> = {
  "bonne affaire": colors.success,
  "à creuser": colors.warning,
  "à éviter": colors.danger,
};

interface Props {
  score: number;
  verdict: Verdict;
}

/** Jauge visuelle du score /10 — barre de progression colorée selon le verdict. */
export function ScoreGauge({ score, verdict }: Props) {
  const clampedScore = Math.min(10, Math.max(0, score));
  const color = VERDICT_COLOR[verdict];

  return (
    <View
      style={styles.container}
      accessible
      accessibilityRole="progressbar"
      accessibilityLabel={`Score ${clampedScore} sur 10`}
    >
      <View style={styles.scoreRow}>
        <Text style={styles.scoreValue}>{clampedScore.toFixed(1)}</Text>
        <Text style={styles.scoreMax}>/10</Text>
      </View>
      <View style={styles.track}>
        <View style={[styles.fill, { width: `${clampedScore * 10}%`, backgroundColor: color }]} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: spacing.sm },
  scoreRow: { flexDirection: "row", alignItems: "flex-end", gap: spacing.xs },
  scoreValue: { ...typography.h1, color: colors.textPrimary },
  scoreMax: { ...typography.body, color: colors.textSecondary, marginBottom: 4 },
  track: {
    height: 12,
    borderRadius: radii.pill,
    backgroundColor: colors.surfaceMuted,
    overflow: "hidden",
  },
  fill: { height: "100%", borderRadius: radii.pill },
});
