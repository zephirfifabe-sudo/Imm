import { StyleSheet, Text, View } from "react-native";
import type { Verdict } from "@previsite/shared";
import { colors, radii, spacing, typography } from "../theme";

const VERDICT_STYLES: Record<Verdict, { background: string; text: string; label: string }> = {
  "bonne affaire": { background: colors.successMuted, text: colors.success, label: "Bonne affaire" },
  "à creuser": { background: colors.warningMuted, text: colors.warning, label: "À creuser" },
  "à éviter": { background: colors.dangerMuted, text: colors.danger, label: "À éviter" },
};

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const style = VERDICT_STYLES[verdict];
  return (
    <View style={[styles.badge, { backgroundColor: style.background }]}>
      <Text style={[styles.text, { color: style.text }]}>{style.label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    alignSelf: "flex-start",
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
    borderRadius: radii.pill,
  },
  text: { ...typography.bodyStrong },
});
