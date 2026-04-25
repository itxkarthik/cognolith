"use client";

import Link from "next/link";
import { AlertTriangle, RefreshCw, Home, AlertCircle } from "lucide-react";

export type ErrorType =
	| "render"
	| "api"
	| "auth"
	| "network"
	| "permission"
	| "unknown";

interface ErrorFallbackProps {
	error: Error;
	type?: ErrorType;
	onReset: () => void;
	onReport?: () => void;
}

/**
 * Determines error type from error message
 */
export function getErrorType(error: Error): ErrorType {
	const message = error.message.toLowerCase();

	if (message.includes("401") || message.includes("unauthorized")) {
		return "auth";
	}
	if (message.includes("403") || message.includes("forbidden")) {
		return "permission";
	}
	if (message.includes("4") && message.includes("0")) {
		return "api";
	}
	if (message.includes("network") || message.includes("fetch")) {
		return "network";
	}
	if (message.includes("render")) {
		return "render";
	}

	return "unknown";
}

/**
 * Renders error-specific UI and messaging
 */
export function ErrorFallback({
	error,
	type,
	onReset,
	onReport,
}: ErrorFallbackProps) {
	const errorType = type || getErrorType(error);

	const errorConfig = {
		render: {
			title: "Something went wrong",
			description: "A rendering error occurred. Try refreshing or going back.",
			icon: AlertTriangle,
			color: "bg-yellow-500/10 border-yellow-500/20 text-yellow-400",
		},
		api: {
			title: "Service Error",
			description:
				"The server encountered an error. Please try again or contact support.",
			icon: AlertCircle,
			color: "bg-red-500/10 border-red-500/20 text-red-400",
		},
		auth: {
			title: "Authentication Error",
			description: "Your session has expired or access is denied. Please log in again.",
			icon: AlertTriangle,
			color: "bg-orange-500/10 border-orange-500/20 text-orange-400",
		},
		network: {
			title: "Network Error",
			description: "Unable to connect to the server. Check your internet connection.",
			icon: AlertCircle,
			color: "bg-blue-500/10 border-blue-500/20 text-blue-400",
		},
		permission: {
			title: "Access Denied",
			description: "You don't have permission to access this resource.",
			icon: AlertTriangle,
			color: "bg-red-500/10 border-red-500/20 text-red-400",
		},
		unknown: {
			title: "Unexpected Error",
			description:
				"An unexpected error occurred. Try refreshing the page or contact support.",
			icon: AlertCircle,
			color: "bg-gray-500/10 border-gray-500/20 text-gray-400",
		},
	};

	const config = errorConfig[errorType];
	const Icon = config.icon;

	return (
		<div className="flex min-h-screen items-center justify-center bg-zinc-950 px-4">
			<div
				className={`w-full max-w-md rounded-xl border ${config.color} bg-zinc-900 p-6 backdrop-blur`}
			>
				{/* Icon */}
				<div className="mb-4 flex justify-center">
					<Icon className="h-12 w-12" strokeWidth={1.5} />
				</div>

				{/* Title */}
				<h1 className="text-center text-xl font-semibold text-zinc-100">
					{config.title}
				</h1>

				{/* Description */}
				<p className="mt-2 text-center text-sm text-zinc-400">{config.description}</p>

				{/* Error Details (development only) */}
				{process.env.NODE_ENV === "development" && (
					<details className="mt-4">
						<summary className="cursor-pointer text-xs font-medium text-zinc-500 hover:text-zinc-300">
							Error Details
						</summary>
						<pre className="mt-2 max-h-32 overflow-auto rounded bg-zinc-950 p-2 text-xs text-zinc-400">
							{error.message}
							{error.stack && `\n\n${error.stack}`}
						</pre>
					</details>
				)}

				{/* Action Buttons */}
				<div className="mt-6 flex flex-col gap-2 sm:flex-row sm:gap-3">
					<button
						onClick={onReset}
						className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-zinc-100 px-4 py-2 text-sm font-medium text-zinc-900 transition hover:bg-white active:scale-95 sm:flex-auto"
					>
						<RefreshCw className="h-4 w-4" />
						Try again
					</button>

					{onReport && (
						<button
							onClick={onReport}
							className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-zinc-700 bg-zinc-800/50 px-4 py-2 text-sm font-medium text-zinc-300 transition hover:bg-zinc-800 active:scale-95 sm:flex-auto"
						>
							Report
						</button>
					)}

					<Link
						href="/"
						className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-zinc-700 bg-zinc-800/50 px-4 py-2 text-sm font-medium text-zinc-300 transition hover:bg-zinc-800 active:scale-95 sm:flex-auto"
					>
						<Home className="h-4 w-4" />
						Home
					</Link>
				</div>

				{/* Help Text */}
				<p className="mt-4 text-center text-xs text-zinc-500">
					If the problem persists, please contact{" "}
					<a
						href="mailto:support@example.com"
						className="text-zinc-400 underline hover:text-zinc-300"
					>
						support
					</a>
				</p>
			</div>
		</div>
	);
}
