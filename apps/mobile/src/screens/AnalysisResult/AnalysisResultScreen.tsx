import { Text, View } from "react-native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { ScreenContainer } from "../../components/ScreenContainer";
import { ScoreGauge } from "../../components/ScoreGauge";
import { VerdictBadge } from "../../components/VerdictBadge";
import { DisclaimerBanner } from "../../components/DisclaimerBanner";
import { PrimaryButton } from "../../components/PrimaryButton";
import { colors, radii, spacing, typography } from "../../theme";
import type { RootStackParamList } from "../../navigation/types";

type Props = NativeStackScreenProps<RootStackParamList, "AnalysisResult">;

function FactorCard({
  title,
  points,
  children,
}: {
  title: string;
  points: number;
  children: React.ReactNode;
}) {
  const pointsColor = points > 0 ? colors.success : points < 0 ? colors.danger : colors.textSecondary;
  const pointsLabel = points > 0 ? `+${points}` : String(points);

  return (
    <View style={factorStyles.card}>
      <View style={factorStyles.header}>
        <Text style={typography.bodyStrong}>{title}</Text>
        <Text style={[typography.bodyStrong, { color: pointsColor }]}>{pointsLabel} pt</Text>
      </View>
      {children}
    </View>
  );
}

export function AnalysisResultScreen({ route, navigation }: Props) {
  const { analysis } = route.params;
  const { scoring, synthesis, vision, input } = analysis;

  return (
    <ScreenContainer>
      <View style={{ gap: spacing.xs }}>
        <Text style={[typography.caption, { color: colors.textSecondary }]}>
          {input.propertyType} · {input.location.commune} ({input.location.postalCode})
        </Text>
        <VerdictBadge verdict={scoring.verdict} />
      </View>

      <ScoreGauge score={scoring.score} verdict={scoring.verdict} />

      <View style={{ gap: spacing.sm }}>
        <Text style={typography.h3}>Synthèse</Text>
        <Text style={[typography.body, { color: colors.textPrimary }]}>{synthesis.resume}</Text>
      </View>

      {synthesis.points_forts.length > 0 ? (
        <View style={{ gap: spacing.xs }}>
          <Text style={[typography.bodyStrong, { color: colors.success }]}>Points forts</Text>
          {synthesis.points_forts.map((point) => (
            <Text key={point} style={typography.body}>
              • {point}
            </Text>
          ))}
        </View>
      ) : null}

      {synthesis.points_faibles.length > 0 ? (
        <View style={{ gap: spacing.xs }}>
          <Text style={[typography.bodyStrong, { color: colors.danger }]}>Points faibles</Text>
          {synthesis.points_faibles.map((point) => (
            <Text key={point} style={typography.body}>
              • {point}
            </Text>
          ))}
        </View>
      ) : null}

      <View style={{ gap: spacing.sm }}>
        <Text style={typography.h3}>Détail du score</Text>

        <FactorCard title="Prix vs marché local" points={scoring.priceFactor.points}>
          <Text style={[typography.caption, { color: colors.textSecondary }]}>
            Prix marché estimé : {scoring.priceFactor.marketPricePerM2} €/m² · Écart :{" "}
            {scoring.priceFactor.deviationPercent > 0 ? "+" : ""}
            {scoring.priceFactor.deviationPercent}%
          </Text>
        </FactorCard>

        <FactorCard title="Impact PEB/DPE" points={scoring.energyFactor.points}>
          <Text style={[typography.caption, { color: colors.textSecondary }]}>
            Classe : {scoring.energyFactor.energyClass ?? "non renseignée"}
            {scoring.energyFactor.estimatedRenovationCostMax > 0
              ? ` · Rénovation énergétique estimée : ${scoring.energyFactor.estimatedRenovationCostMin} – ${scoring.energyFactor.estimatedRenovationCostMax} €`
              : ""}
          </Text>
        </FactorCard>

        <FactorCard title="Travaux visibles en photo" points={scoring.workFactor.points}>
          <Text style={[typography.caption, { color: colors.textSecondary }]}>
            Étendue : {scoring.workFactor.extent} · Budget estimé : {vision.budget_travaux_estime_min}{" "}
            – {vision.budget_travaux_estime_max} €
          </Text>
        </FactorCard>
      </View>

      <DisclaimerBanner />

      <PrimaryButton label="Retour à l'accueil" onPress={() => navigation.popToTop()} />
    </ScreenContainer>
  );
}

const factorStyles = {
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: spacing.xs,
  },
  header: {
    flexDirection: "row" as const,
    justifyContent: "space-between" as const,
    alignItems: "center" as const,
  },
};
