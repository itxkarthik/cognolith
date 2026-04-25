"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/authStore";

export default function Home() {
	const router = useRouter();
	const { isAuthenticated, hasHydrated } = useAuthStore();

	useEffect(() => {
		if (hasHydrated) {
			if (isAuthenticated) {
				router.push("/dashboard");
			} else {
				router.push("/auth/login");
			}
		}
	}, [hasHydrated, isAuthenticated, router]);

	// Show loading state while checking authentication
	return (
		<div className="min-h-screen bg-[#131313] flex items-center justify-center">
			<div className="text-center">
				<div className="animate-spin rounded-full h-12 w-12 border-2 border-[#c0c1ff] border-t-[#bcff5f] mx-auto mb-4"></div>
				<p className="text-sm text-[#8a8a8a]">Loading...</p>
			</div>
		</div>
	);
}
