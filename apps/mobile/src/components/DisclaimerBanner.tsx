import { StyleSheet, Text, View } from "react-native";
import { DISCLAIMER_TEXT } from "@previsite/shared";
import { colors, radii, spacing, typography } from "../theme";

/** Rappel légal affiché sur l'accueil, le résultat et le footer — jamais optionnel. */
export function DisclaimerBanner() {
  return (
    <View style={styles.container} accessibilityRole="text">
      <Text style={styles.title}>À lire avant tout</Text>
      <Text style={styles.text}>{DISCLAIMER_TEXT}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.surfaceMuted,
    borderRadius: radii.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    gap: spacing.xs,
  },
  title: { ...typography.bodyStrong, color: colors.textPrimary },
  text: { ...typography.caption, color: colors.textSecondary },
});
