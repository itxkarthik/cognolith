"use client";

import type { ReactNode } from "react";
import { Component } from "react";
import { ErrorFallback, type ErrorType, getErrorType } from "./ErrorFallback";

interface ErrorBoundaryProps {
	children: ReactNode;
	fallback?: ReactNode;
	onError?: (error: Error, errorInfo: React.ErrorInfo) => void;
	level?: "page" | "section" | "component";
	showDetails?: boolean;
}

interface ErrorBoundaryState {
	hasError: boolean;
	error?: Error;
	errorType?: ErrorType;
}

/**
 * Error Boundary Component
 *
 * Catches rendering errors and displays fallback UI with recovery options.
 * Supports multiple error types and error reporting.
 *
 * @param level - 'page' (full screen), 'section' (major component), 'component' (inline)
 * @param onError - Callback for error reporting/logging
 * @param showDetails - Show error details in development mode
 *
 * @example
 * <ErrorBoundary level="section" onError={reportToSentry}>
 *   <Dashboard />
 * </ErrorBoundary>
 */
export class ErrorBoundary extends Component<
	ErrorBoundaryProps,
	ErrorBoundaryState
> {
	public constructor(props: ErrorBoundaryProps) {
		super(props);
		this.state = { hasError: false };
	}

	public static getDerivedStateFromError(error: Error): ErrorBoundaryState {
		const errorType = getErrorType(error);
		return { hasError: true, error, errorType };
	}

	public componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
		// Log to console in development
		console.error("ErrorBoundary captured:", error);
		console.error("Component Stack:", errorInfo.componentStack);

		// Call optional error handler for reporting/analytics
		if (this.props.onError) {
			this.props.onError(error, errorInfo);
		}

		// Log to external service in production
		if (process.env.NODE_ENV === "production") {
			this.reportError(error, errorInfo);
		}
	}

	/**
	 * Report error to external service (e.g., Sentry, LogRocket)
	 */
	private readonly reportError = async (
		error: Error,
		errorInfo: React.ErrorInfo
	): Promise<void> => {
		try {
			// Send to your error reporting service
			const payload = {
				message: error.message,
				stack: error.stack,
				componentStack: errorInfo.componentStack,
				timestamp: new Date().toISOString(),
				userAgent: typeof window !== "undefined" ? navigator.userAgent : "unknown",
				url: typeof window !== "undefined" ? window.location.href : "unknown",
			};

			// Example: Send to your logging endpoint
			await fetch("/api/errors", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify(payload),
			}).catch(() => {
				// Silently fail - don't throw if error reporting fails
			});
		} catch {
			// Prevent error reporting from causing cascading errors
		}
	};

	private readonly reset = (): void => {
		this.setState({ hasError: false, error: undefined, errorType: undefined });
	};

	private readonly handleReport = (): void => {
		if (this.state.error) {
			this.reportError(this.state.error, {
				componentStack: this.state.error.stack || "",
			});
			alert("Error report sent. Thank you for your feedback.");
		}
	};

	private readonly renderMinimalError = (): ReactNode => {
		return (
			<div className="flex items-center justify-center px-4 py-6">
				<div className="rounded-lg border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-400">
					<p className="font-medium">Component Error</p>
					<p className="mt-1 text-red-300">
						{this.state.error?.message ?? "An error occurred"}
					</p>
					<button
						onClick={this.reset}
						className="mt-3 inline-block rounded bg-red-500 px-3 py-1 text-xs font-medium text-white hover:bg-red-600"
					>
						Retry
					</button>
				</div>
			</div>
		);
	};

	public render(): ReactNode {
		if (this.state.hasError) {
			// Custom fallback if provided
			if (this.props.fallback) {
				return this.props.fallback;
			}

			// Component level - minimal error display
			if (this.props.level === "component") {
				return this.renderMinimalError();
			}

			// Section or page level - full error UI
			if (this.state.error) {
				return (
					<ErrorFallback
						error={this.state.error}
						type={this.state.errorType}
						onReset={this.reset}
						onReport={this.handleReport}
					/>
				);
			}
		}

		return this.props.children;
	}
}
