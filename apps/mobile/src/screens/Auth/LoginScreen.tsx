import { useState } from "react";
import { Text, View } from "react-native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { loginSchema } from "@previsite/shared";
import { ScreenContainer } from "../../components/ScreenContainer";
import { FormField, TextField } from "../../components/FormField";
import { PrimaryButton } from "../../components/PrimaryButton";
import { loginRequest } from "../../services/api/auth.api";
import { useAuthStore } from "../../store/authStore";
import { ApiRequestError } from "../../services/api/client";
import { colors, spacing, typography } from "../../theme";
import type { RootStackParamList } from "../../navigation/types";

type Props = NativeStackScreenProps<RootStackParamList, "Login">;

export function LoginScreen({ navigation }: Props) {
  const setSession = useAuthStore((state) => state.setSession);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    setFormError(null);
    const parsed = loginSchema.safeParse({ email, password });
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
      const { token, user } = await loginRequest(parsed.data.email, parsed.data.password);
      await setSession(token, user);
    } catch (error) {
      setFormError(error instanceof ApiRequestError ? error.message : "Connexion impossible.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ScreenContainer>
      <View style={{ gap: spacing.xs, marginTop: spacing.xl }}>
        <Text style={[typography.h1, { color: colors.primary }]}>PréVisite</Text>
        <Text style={[typography.body, { color: colors.textSecondary }]}>
          Connecte-toi pour analyser un bien avant de le visiter.
        </Text>
      </View>

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
          textContentType="password"
          placeholder="••••••••"
        />
      </FormField>

      {formError ? (
        <Text style={{ color: colors.danger }} accessibilityRole="alert">
          {formError}
        </Text>
      ) : null}

      <PrimaryButton label="Se connecter" onPress={handleSubmit} loading={isSubmitting} />
      <PrimaryButton
        label="Créer un compte"
        variant="ghost"
        onPress={() => navigation.navigate("Register")}
      />
    </ScreenContainer>
  );
}
