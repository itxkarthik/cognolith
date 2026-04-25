"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState, useEffect } from "react";
import { motion } from "motion/react";

import { getCurrentUser, login } from "@/lib/api/auth";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { useAuthStore } from "@/store/authStore";

export default function LoginPage() {
	const router = useRouter();
	const setAuth = useAuthStore((state) => state.setAuth);
	const { isAuthenticated, hasHydrated } = useAuthStore();

	const [email, setEmail] = useState("");
	const [password, setPassword] = useState("");
	const [isSubmitting, setIsSubmitting] = useState(false);
	const [error, setError] = useState<string | null>(null);

	// Redirect to dashboard if already authenticated
	useEffect(() => {
		if (hasHydrated && isAuthenticated) {
			router.push("/dashboard");
		}
	}, [hasHydrated, isAuthenticated, router]);

	const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		setError(null);
		setIsSubmitting(true);

		try {
			await login({ email, password });
			const user = await getCurrentUser();

			setAuth({
				user,
			});

			router.push("/dashboard");
		} catch (err) {
			setError(err instanceof Error ? err.message : "Unable to login.");
		} finally {
			setIsSubmitting(false);
		}
	};

	return (
		<div className="min-h-screen bg-[#131313] flex items-center justify-center px-4">
			{/* Ambient glow effect */}
			<div className="absolute top-20 -left-40 w-80 h-80 bg-[#c0c1ff]/5 rounded-full blur-3xl"></div>
			<div className="absolute bottom-20 -right-40 w-80 h-80 bg-[#bcff5f]/5 rounded-full blur-3xl"></div>

			<motion.div
				initial={{ opacity: 0, y: 20 }}
				animate={{ opacity: 1, y: 0 }}
				transition={{ duration: 0.5, ease: "easeOut" }}
				className="relative w-full max-w-md"
			>
				<div className="glass-panel border border-[#1f1f1f] rounded-2xl p-8 backdrop-blur-xl">
					{/* Header */}
					<div className="mb-8">
						<p className="text-xs uppercase tracking-widest text-[#98989b] font-medium">Welcome Back</p>
						<h1 className="mt-2 text-3xl font-bold text-white">Sign in</h1>
						<p className="mt-2 text-sm text-[#98989b]">Access your knowledge workspace</p>
					</div>

					{/* Form */}
					<form onSubmit={onSubmit} className="space-y-5">
						{/* Email */}
						<div>
							<label className="block text-xs uppercase tracking-widest text-[#c0c1ff] font-medium mb-2">
								Email
							</label>
							<input
								type="email"
								required
								value={email}
								onChange={(event) => setEmail(event.target.value)}
								placeholder="you@example.com"
								className="w-full px-4 py-3 rounded-lg bg-[#1f1f1f] border border-[#2a2a2a] text-white placeholder-[#656569] focus:outline-none focus:border-[#c0c1ff] focus:ring-1 focus:ring-[#c0c1ff]/20 transition-all"
							/>
						</div>

						{/* Password */}
						<div>
							<label className="block text-xs uppercase tracking-widest text-[#c0c1ff] font-medium mb-2">
								Password
							</label>
							<input
								type="password"
								required
								value={password}
								onChange={(event) => setPassword(event.target.value)}
								placeholder="••••••••"
								className="w-full px-4 py-3 rounded-lg bg-[#1f1f1f] border border-[#2a2a2a] text-white placeholder-[#656569] focus:outline-none focus:border-[#c0c1ff] focus:ring-1 focus:ring-[#c0c1ff]/20 transition-all"
							/>
						</div>

						{/* Error Message */}
						{error && (
							<div className="rounded-lg border border-[#ff4d6d]/30 bg-[#ff4d6d]/10 px-4 py-3 text-sm text-[#ff6b7a]">
								{error}
							</div>
						)}

						{/* Submit Button */}
						<button
							type="submit"
							disabled={isSubmitting}
							className="w-full py-3 px-4 rounded-lg bg-gradient-to-r from-[#c0c1ff] to-[#a6a7e0] text-[#131313] font-semibold uppercase tracking-wider hover:shadow-lg hover:shadow-[#c0c1ff]/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 mt-6"
						>
							{isSubmitting ? (
								<LoadingSpinner className="text-[#131313]" />
							) : (
								"Sign in"
							)}
						</button>
					</form>

					{/* Divider */}
					<div className="my-6 flex items-center gap-3">
						<div className="flex-1 h-px bg-[#2a2a2a]"></div>
						<p className="text-xs text-[#656569]">NEW HERE?</p>
						<div className="flex-1 h-px bg-[#2a2a2a]"></div>
					</div>

					{/* Sign Up Link */}
					<p className="text-center text-sm text-[#98989b]">
						No account yet?{" "}
						<Link href="/auth/register" className="text-[#bcff5f] font-semibold hover:underline">
							Create one
						</Link>
					</p>
				</div>
			</motion.div>
		</div>
	);
}
