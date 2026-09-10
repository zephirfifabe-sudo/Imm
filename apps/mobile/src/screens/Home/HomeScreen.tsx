import { Text, View } from "react-native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import type { CompositeScreenProps } from "@react-navigation/native";
import type { BottomTabScreenProps } from "@react-navigation/bottom-tabs";
import { ScreenContainer } from "../../components/ScreenContainer";
import { PrimaryButton } from "../../components/PrimaryButton";
import { DisclaimerBanner } from "../../components/DisclaimerBanner";
import { useAuthStore } from "../../store/authStore";
import { colors, spacing, typography } from "../../theme";
import type { RootStackParamList, TabParamList } from "../../navigation/types";

type Props = CompositeScreenProps<
  BottomTabScreenProps<TabParamList, "Home">,
  NativeStackScreenProps<RootStackParamList>
>;

const VALUE_POINTS = [
  "Un score sur 10 basé sur des règles claires, pas une boîte noire.",
  "L'écart entre le prix demandé et le prix moyen du marché local.",
  "Une estimation de l'étendue des travaux visibles sur tes photos.",
  "L'impact de la classe PEB/DPE sur le budget à prévoir.",
];

export function HomeScreen({ navigation }: Props) {
  const user = useAuthStore((state) => state.user);

  return (
    <ScreenContainer>
      <View style={{ gap: spacing.xs, marginTop: spacing.md }}>
        <Text style={[typography.h1, { color: colors.primary }]}>
          {user?.fullName ? `Bonjour ${user.fullName.split(" ")[0]}` : "Bonjour"}
        </Text>
        <Text style={[typography.body, { color: colors.textSecondary }]}>
          Sais-tu vraiment si ce bien vaut le déplacement ? PréVisite te donne une première
          indication objective avant de prendre rendez-vous.
        </Text>
      </View>

      <View style={{ gap: spacing.sm }}>
        {VALUE_POINTS.map((point) => (
          <View key={point} style={{ flexDirection: "row", gap: spacing.sm }}>
            <Text style={{ color: colors.primaryMuted }}>—</Text>
            <Text style={[typography.body, { color: colors.textPrimary, flex: 1 }]}>{point}</Text>
          </View>
        ))}
      </View>

      <PrimaryButton label="Analyser un bien" onPress={() => navigation.navigate("AnalysisForm")} />

      <DisclaimerBanner />
    </ScreenContainer>
  );
}
