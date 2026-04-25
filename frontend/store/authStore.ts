import { create } from "zustand";

import type { User } from "@/types";

interface AuthState {
	user: User | null;
	isAuthenticated: boolean;
	hasHydrated: boolean;
	setAuth: (payload: { user: User }) => void;
	setUser: (user: User | null) => void;
	clearAuth: () => void;
	setHasHydrated: (hasHydrated: boolean) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
	user: null,
	isAuthenticated: false,
	hasHydrated: false,
	setAuth: ({ user }) => {
		set({ user, isAuthenticated: true });
	},
	setUser: (user) => set({ user }),
	clearAuth: () => {
		set({
			user: null,
			isAuthenticated: false,
		});
	},
	setHasHydrated: (hasHydrated) => set({ hasHydrated }),
}));
