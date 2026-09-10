import { useCallback, useState } from "react";
import { ActivityIndicator, Alert, Pressable, Text, View } from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { ScreenContainer } from "../../components/ScreenContainer";
import { PrimaryButton } from "../../components/PrimaryButton";
import { useAuthStore } from "../../store/authStore";
import {
  createPaymentIntent,
  fetchCreditPacks,
  fetchCreditSummary,
  type CreditSummary,
} from "../../services/api/credits.api";
import { ApiRequestError } from "../../services/api/client";
import { colors, radii, spacing, typography } from "../../theme";

interface Pack {
  id: string;
  label: string;
  credits: number;
  priceCents: number;
}

export function AccountScreen() {
  const user = useAuthStore((state) => state.user);
  const signOut = useAuthStore((state) => state.signOut);

  const [summary, setSummary] = useState<CreditSummary | null>(null);
  const [packs, setPacks] = useState<Pack[]>([]);
  const [isLoading, setLoading] = useState(true);
  const [purchasingPackId, setPurchasingPackId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [creditSummary, { packs: fetchedPacks }] = await Promise.all([
        fetchCreditSummary(),
        fetchCreditPacks(),
      ]);
      setSummary(creditSummary);
      setPacks(fetchedPacks);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  async function handlePurchase(pack: Pack) {
    setPurchasingPackId(pack.id);
    try {
      await createPaymentIntent(pack.id);
      // Le paiement Stripe est initié côté serveur (mode test). La saisie de
      // carte via le Payment Sheet natif Stripe nécessite un build de
      // développement personnalisé (incompatible avec Expo Go) : elle sera
      // branchée à l'étape du build EAS, hors périmètre de ce test rapide.
      Alert.alert(
        "Paiement initié",
        "L'intention de paiement a été créée côté serveur en mode test. L'écran de saisie de carte Stripe sera intégré lors du passage à un build natif (EAS).",
      );
    } catch (error) {
      Alert.alert(
        "Paiement indisponible",
        error instanceof ApiRequestError ? error.message : "Réessaie dans un instant.",
      );
    } finally {
      setPurchasingPackId(null);
    }
  }

  if (isLoading) {
    return (
      <ScreenContainer style={{ alignItems: "center", justifyContent: "center" }}>
        <ActivityIndicator color={colors.primary} />
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer>
      <View style={{ gap: spacing.xs, marginTop: spacing.md }}>
        <Text style={typography.h2}>Mon compte</Text>
        <Text style={[typography.body, { color: colors.textSecondary }]}>{user?.email}</Text>
      </View>

      <View
        style={{
          backgroundColor: colors.primary,
          borderRadius: radii.md,
          padding: spacing.lg,
          gap: spacing.xs,
        }}
      >
        <Text style={[typography.body, { color: colors.textOnPrimaryMuted }]}>Solde de crédits</Text>
        <Text style={[typography.h1, { color: colors.textOnPrimary }]}>{summary?.creditBalance ?? 0}</Text>
        <Text style={[typography.caption, { color: colors.textOnPrimaryMuted }]}>
          {summary?.freeAnalysesRemaining ?? 0} analyse(s) gratuite(s) restante(s)
        </Text>
      </View>

      <View style={{ gap: spacing.sm }}>
        <Text style={typography.h3}>Packs de crédits</Text>
        {packs.map((pack) => (
          <View
            key={pack.id}
            style={{
              flexDirection: "row",
              justifyContent: "space-between",
              alignItems: "center",
              borderWidth: 1,
              borderColor: colors.border,
              borderRadius: radii.md,
              padding: spacing.md,
            }}
          >
            <View>
              <Text style={typography.bodyStrong}>{pack.label}</Text>
              <Text style={[typography.caption, { color: colors.textSecondary }]}>
                {(pack.priceCents / 100).toFixed(2)} €
              </Text>
            </View>
            <Pressable
              accessibilityRole="button"
              onPress={() => handlePurchase(pack)}
              disabled={purchasingPackId === pack.id}
              style={{
                backgroundColor: colors.primary,
                borderRadius: radii.sm,
                paddingVertical: spacing.sm,
                paddingHorizontal: spacing.md,
                opacity: purchasingPackId === pack.id ? 0.6 : 1,
              }}
            >
              <Text style={{ color: colors.textOnPrimary, fontWeight: "600" }}>Acheter</Text>
            </Pressable>
          </View>
        ))}
      </View>

      <PrimaryButton label="Se déconnecter" variant="secondary" onPress={() => signOut()} />
    </ScreenContainer>
  );
}
