import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { Text } from "react-native";
import { HomeScreen } from "../screens/Home/HomeScreen";
import { HistoryScreen } from "../screens/History/HistoryScreen";
import { AccountScreen } from "../screens/Account/AccountScreen";
import { colors } from "../theme";
import type { TabParamList } from "./types";

const Tab = createBottomTabNavigator<TabParamList>();

const TAB_ICONS: Record<keyof TabParamList, string> = {
  Home: "🏠",
  History: "🕘",
  Account: "👤",
};

export function TabNavigator() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textSecondary,
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border },
        tabBarIcon: () => <Text>{TAB_ICONS[route.name]}</Text>,
      })}
    >
      <Tab.Screen name="Home" component={HomeScreen} options={{ tabBarLabel: "Accueil" }} />
      <Tab.Screen name="History" component={HistoryScreen} options={{ tabBarLabel: "Historique" }} />
      <Tab.Screen name="Account" component={AccountScreen} options={{ tabBarLabel: "Compte" }} />
    </Tab.Navigator>
  );
}
