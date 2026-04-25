"use client";

import { useCallback } from "react";

import { logout as logoutRequest } from "@/lib/api/auth";
import { useAuthStore } from "@/store/authStore";

export function useAuth() {
	const user = useAuthStore((state) => state.user);
	const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
	const hasHydrated = useAuthStore((state) => state.hasHydrated);
	const clearAuth = useAuthStore((state) => state.clearAuth);

	const logout = useCallback(async () => {
		try {
			await logoutRequest();
		} catch {
			// Local auth state should still be cleared if server logout fails.
		} finally {
			clearAuth();
		}
	}, [clearAuth]);

	return {
		user,
		isAuthenticated,
		hasHydrated,
		logout,
	};
}
