import { useCallback, useState } from "react";
import { ActivityIndicator, FlatList, Pressable, RefreshControl, Text, View } from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import type { CompositeScreenProps } from "@react-navigation/native";
import type { BottomTabScreenProps } from "@react-navigation/bottom-tabs";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import type { AnalysisRecord } from "@previsite/shared";
import { ScreenContainer } from "../../components/ScreenContainer";
import { VerdictBadge } from "../../components/VerdictBadge";
import { fetchAnalysisHistory } from "../../services/api/analyses.api";
import { ApiRequestError } from "../../services/api/client";
import { colors, radii, spacing, typography } from "../../theme";
import type { RootStackParamList, TabParamList } from "../../navigation/types";

type Props = CompositeScreenProps<
  BottomTabScreenProps<TabParamList, "History">,
  NativeStackScreenProps<RootStackParamList>
>;

export function HistoryScreen({ navigation }: Props) {
  const [analyses, setAnalyses] = useState<AnalysisRecord[]>([]);
  const [isLoading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const { analyses: fetched } = await fetchAnalysisHistory();
      setAnalyses(fetched);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Impossible de charger l'historique.");
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  if (isLoading) {
    return (
      <ScreenContainer scroll={false} style={{ alignItems: "center", justifyContent: "center" }}>
        <ActivityIndicator color={colors.primary} />
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer scroll={false} style={{ padding: 0 }}>
      <FlatList
        data={analyses}
        keyExtractor={(item) => item.id}
        contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm, flexGrow: 1 }}
        refreshControl={<RefreshControl refreshing={isLoading} onRefresh={load} />}
        ListHeaderComponent={<Text style={[typography.h2, { marginBottom: spacing.sm }]}>Historique</Text>}
        ListEmptyComponent={
          <Text style={[typography.body, { color: colors.textSecondary }]}>
            {error ?? "Aucune analyse pour l'instant. Lance ta première analyse depuis l'accueil."}
          </Text>
        }
        renderItem={({ item }) => (
          <Pressable
            accessibilityRole="button"
            onPress={() => navigation.navigate("AnalysisResult", { analysis: item })}
            style={{
              backgroundColor: colors.surface,
              borderWidth: 1,
              borderColor: colors.border,
              borderRadius: radii.md,
              padding: spacing.md,
              gap: spacing.xs,
            }}
          >
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <Text style={typography.bodyStrong}>
                {item.input.propertyType} · {item.input.location.commune}
              </Text>
              <Text style={typography.bodyStrong}>{item.scoring.score.toFixed(1)}/10</Text>
            </View>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <Text style={[typography.caption, { color: colors.textSecondary }]}>
                {new Date(item.createdAt).toLocaleDateString("fr-BE")}
              </Text>
              <VerdictBadge verdict={item.scoring.verdict} />
            </View>
          </Pressable>
        )}
      />
    </ScreenContainer>
  );
}
