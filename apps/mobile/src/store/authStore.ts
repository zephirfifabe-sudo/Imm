import { create } from "zustand";
import * as SecureStore from "expo-secure-store";

const TOKEN_KEY = "previsite_auth_token";

export interface AuthUser {
  id: string;
  email: string;
  fullName: string | null;
  creditBalance: number;
  freeAnalysesUsed: number;
}

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  isHydrating: boolean;
  hydrate: () => Promise<void>;
  setSession: (token: string, user: AuthUser) => Promise<void>;
  updateUser: (user: AuthUser) => void;
  signOut: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  isHydrating: true,

  hydrate: async () => {
    const token = await SecureStore.getItemAsync(TOKEN_KEY);
    set({ token, isHydrating: false });
  },

  setSession: async (token, user) => {
    await SecureStore.setItemAsync(TOKEN_KEY, token);
    set({ token, user });
  },

  updateUser: (user) => set({ user }),

  signOut: async () => {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    set({ token: null, user: null });
  },
}));
