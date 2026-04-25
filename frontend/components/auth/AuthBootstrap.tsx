"use client";

import { useEffect } from "react";

import { getCurrentUser } from "@/lib/api/auth";
import { useAuthStore } from "@/store/authStore";

export function AuthBootstrap() {
	const setAuth = useAuthStore((state) => state.setAuth);
	const clearAuth = useAuthStore((state) => state.clearAuth);
	const setHasHydrated = useAuthStore((state) => state.setHasHydrated);

	useEffect(() => {
		let mounted = true;

		async function bootstrapSession() {
			try {
				const user = await getCurrentUser();
				if (mounted) {
					setAuth({ user });
				}
			} catch {
				if (mounted) {
					clearAuth();
				}
			} finally {
				if (mounted) {
					setHasHydrated(true);
				}
			}
		}

		bootstrapSession();

		return () => {
			mounted = false;
		};
	}, [clearAuth, setAuth, setHasHydrated]);

	return null;
}
