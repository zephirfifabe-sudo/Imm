import Constants from "expo-constants";

/**
 * URL de base de l'API backend. En développement avec Expo Go, on ne peut
 * pas utiliser "localhost" (qui pointerait vers le téléphone/l'émulateur
 * lui-même) : on récupère l'hôte du bundler Metro pour construire l'URL du
 * poste de développement. En build de prod, EXPO_PUBLIC_API_URL doit être
 * défini à l'URL réelle du backend déployé.
 */
function resolveDevApiUrl(): string {
  const hostUri = Constants.expoConfig?.hostUri;
  const host = hostUri?.split(":")[0];
  return host ? `http://${host}:4000` : "http://localhost:4000";
}

export const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? resolveDevApiUrl();
