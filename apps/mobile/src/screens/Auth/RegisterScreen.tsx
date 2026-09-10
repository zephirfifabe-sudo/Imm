import { useState } from "react";
import { Text, View } from "react-native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { registerSchema, FREE_ANALYSES_PER_ACCOUNT } from "@previsite/shared";
import { ScreenContainer } from "../../components/ScreenContainer";
import { FormField, TextField } from "../../components/FormField";
import { PrimaryButton } from "../../components/PrimaryButton";
import { registerRequest } from "../../services/api/auth.api";
import { useAuthStore } from "../../store/authStore";
import { ApiRequestError } from "../../services/api/client";
import { colors, spacing, typography } from "../../theme";
import type { RootStackParamList } from "../../navigation/types";

type Props = NativeStackScreenProps<RootStackParamList, "Register">;

export function RegisterScreen({ navigation }: Props) {
  const setSession = useAuthStore((state) => state.setSession);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    setFormError(null);
    const parsed = registerSchema.safeParse({ email, password, fullName: fullName || undefined });
    if (!parsed.success) {
      const errors: Record<string, string> = {};
      parsed.error.issues.forEach((issue) => {
        errors[String(issue.path[0])] = issue.message;
      });
      setFieldErrors(errors);
      return;
    }
    setFieldErrors({});
    setSubmitting(true);
    try {
      const { token, user } = await registerRequest(
        parsed.data.email,
        parsed.data.password,
        parsed.data.fullName,
      );
      await setSession(token, user);
    } catch (error) {
      setFormError(error instanceof ApiRequestError ? error.message : "Inscription impossible.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ScreenContainer>
      <View style={{ gap: spacing.xs, marginTop: spacing.xl }}>
        <Text style={[typography.h1, { color: colors.primary }]}>Créer un compte</Text>
        <Text style={[typography.body, { color: colors.textSecondary }]}>
          {FREE_ANALYSES_PER_ACCOUNT} analyses gratuites à vie pour démarrer, sans engagement.
        </Text>
      </View>

      <FormField label="Nom complet" error={fieldErrors.fullName}>
        <TextField value={fullName} onChangeText={setFullName} placeholder="Prénom Nom" />
      </FormField>

      <FormField label="Email" error={fieldErrors.email} required>
        <TextField
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          keyboardType="email-address"
          textContentType="emailAddress"
          placeholder="toi@exemple.be"
        />
      </FormField>

      <FormField label="Mot de passe" error={fieldErrors.password} required>
        <TextField
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          textContentType="newPassword"
          placeholder="8 caractères minimum"
        />
      </FormField>

      {formError ? (
        <Text style={{ color: colors.danger }} accessibilityRole="alert">
          {formError}
        </Text>
      ) : null}

      <PrimaryButton label="Créer mon compte" onPress={handleSubmit} loading={isSubmitting} />
      <PrimaryButton
        label="J'ai déjà un compte"
        variant="ghost"
        onPress={() => navigation.navigate("Login")}
      />
    </ScreenContainer>
  );
}
