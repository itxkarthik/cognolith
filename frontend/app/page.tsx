"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/authStore";
import { Card, CardContent } from "@/components/ui";
import { Loader2 } from "lucide-react";

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
		<div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#0a0e27] px-4">
			{/* Animated background grid */}
			<div className="absolute inset-0 opacity-30">
				<div className="absolute inset-0" style={{
					backgroundImage: 'linear-gradient(rgba(0, 255, 255, 0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 255, 255, 0.1) 1px, transparent 1px)',
					backgroundSize: '50px 50px',
					animation: 'grid-fade 4s ease-in-out infinite'
				}} />
			</div>

			{/* Glowing orbs */}
			<div className="absolute inset-0 pointer-events-none">
				<div className="absolute top-1/4 left-1/3 w-96 h-96 bg-cyan-500/20 rounded-full blur-3xl" style={{ animation: 'float-up 6s ease-in-out infinite' }} />
				<div className="absolute bottom-1/4 right-1/4 w-72 h-72 bg-teal-500/20 rounded-full blur-3xl" style={{ animation: 'float-up 8s ease-in-out infinite, 1s' }} />
			</div>

			<Card className="relative w-full max-w-md border border-cyan-500/30 bg-[#1a1f3a]/60 shadow-2xl backdrop-blur-xl">
				<CardContent className="flex flex-col items-center justify-center gap-6 py-12 px-8">
					<div className="relative">
						<div className="absolute inset-0 bg-gradient-to-r from-cyan-500 to-teal-500 rounded-3xl blur-lg opacity-50" />
						<div className="relative flex h-16 w-16 items-center justify-center rounded-3xl bg-[#0a0e27] border border-cyan-500/50">
							<Loader2 className="h-8 w-8 animate-spin text-cyan-500" />
						</div>
					</div>

					<div className="text-center space-y-2">
						<p className="text-lg font-semibold text-cyan-50" style={{ textShadow: '0 0 10px rgba(0, 255, 255, 0.5)' }}>Loading workspace</p>
						<p className="text-sm text-cyan-200/70">Initializing your personal knowledge vault...</p>
					</div>

					{/* Animated progress bar */}
					<div className="w-full h-1 bg-[#252d4a] rounded-full overflow-hidden">
						<div
							className="h-full bg-gradient-to-r from-cyan-500 via-teal-500 to-cyan-500 rounded-full"
							style={{
								animation: 'scaleX 2s ease-in-out infinite',
								transformOrigin: 'left'
							}}
						/>
					</div>
				</CardContent>
			</Card>

			<style jsx>{`
				@keyframes scaleX {
					0%, 100% { transform: scaleX(0.1); }
					50% { transform: scaleX(1); }
				}
			`}</style>
		</div>
	);
}
