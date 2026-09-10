import { useEffect } from "react";
import { ActivityIndicator, View } from "react-native";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { TabNavigator } from "./TabNavigator";
import { LoginScreen } from "../screens/Auth/LoginScreen";
import { RegisterScreen } from "../screens/Auth/RegisterScreen";
import { AnalysisFormScreen } from "../screens/AnalysisForm/AnalysisFormScreen";
import { AnalysisResultScreen } from "../screens/AnalysisResult/AnalysisResultScreen";
import { useAuthStore } from "../store/authStore";
import { fetchCurrentUser } from "../services/api/auth.api";
import { colors } from "../theme";
import type { RootStackParamList } from "./types";

const Stack = createNativeStackNavigator<RootStackParamList>();

export function RootNavigator() {
  const { token, isHydrating, hydrate, updateUser, signOut } = useAuthStore();

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  useEffect(() => {
    if (!token) return;
    fetchCurrentUser()
      .then(({ user }) => updateUser(user))
      .catch(() => signOut());
  }, [token, updateUser, signOut]);

  if (isHydrating) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.background }}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        {token ? (
          <>
            <Stack.Screen name="Tabs" component={TabNavigator} />
            <Stack.Screen
              name="AnalysisForm"
              component={AnalysisFormScreen}
              options={{ headerShown: true, title: "Analyser un bien" }}
            />
            <Stack.Screen
              name="AnalysisResult"
              component={AnalysisResultScreen}
              options={{ headerShown: true, title: "Résultat de l'analyse" }}
            />
          </>
        ) : (
          <>
            <Stack.Screen name="Login" component={LoginScreen} />
            <Stack.Screen name="Register" component={RegisterScreen} />
          </>
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}
