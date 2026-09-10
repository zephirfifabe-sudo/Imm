import { PropsWithChildren } from "react";
import { ScrollView, StyleSheet, View, ViewStyle } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors, spacing } from "../theme";

interface Props extends PropsWithChildren {
  scroll?: boolean;
  style?: ViewStyle;
}

/** Conteneur d'écran standard : safe area + padding cohérent + fond de l'app. */
export function ScreenContainer({ children, scroll = true, style }: Props) {
  const Container = scroll ? ScrollView : View;
  return (
    <SafeAreaView style={styles.safeArea} edges={["top", "left", "right"]}>
      <Container
        style={scroll ? styles.scroll : [styles.content, style]}
        contentContainerStyle={scroll ? [styles.content, style] : undefined}
        keyboardShouldPersistTaps="handled"
      >
        {children}
      </Container>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.background },
  scroll: { flex: 1 },
  content: { padding: spacing.lg, gap: spacing.md, flexGrow: 1 },
});
