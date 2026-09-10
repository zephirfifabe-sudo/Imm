import { PropsWithChildren } from "react";
import { StyleSheet, Text, TextInput, TextInputProps, View } from "react-native";
import { colors, radii, spacing, typography } from "../theme";

interface FormFieldProps extends PropsWithChildren {
  label: string;
  error?: string;
  required?: boolean;
}

/** Enveloppe un champ (TextInput ou sélecteur custom) avec un label accessible et un message d'erreur. */
export function FormField({ label, error, required, children }: FormFieldProps) {
  return (
    <View style={styles.container}>
      <Text style={styles.label} nativeID={`${label}-label`}>
        {label}
        {required ? " *" : ""}
      </Text>
      {children}
      {error ? (
        <Text style={styles.error} accessibilityRole="alert">
          {error}
        </Text>
      ) : null}
    </View>
  );
}

export function TextField(props: TextInputProps) {
  return (
    <TextInput
      placeholderTextColor={colors.textSecondary}
      style={styles.input}
      {...props}
    />
  );
}

const styles = StyleSheet.create({
  container: { gap: spacing.xs },
  label: { ...typography.bodyStrong, color: colors.textPrimary },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    fontSize: 15,
    color: colors.textPrimary,
    backgroundColor: colors.surface,
  },
  error: { ...typography.caption, color: colors.danger },
});
