import { NextRequest, NextResponse } from "next/server";

interface ErrorPayload {
	message: string;
	stack?: string;
	componentStack?: string;
	timestamp: string;
	userAgent: string;
	url: string;
}

/**
 * Error Reporting Endpoint
 *
 * Receives client-side errors from ErrorBoundary and logs them
 * for monitoring and debugging purposes.
 *
 * In production, you would send these to:
 * - Sentry
 * - LogRocket
 * - DataDog
 * - Your custom logging service
 */
export async function POST(request: NextRequest) {
	try {
		const payload: ErrorPayload = await request.json();

		// Log to console (in development or for debugging)
		console.error("[Client Error Report]", {
			message: payload.message,
			timestamp: payload.timestamp,
			url: payload.url,
		});

		// Here you would send to your error tracking service
		// Example: await sendToSentry(payload);
		// Example: await saveToDatabase(payload);

		return NextResponse.json(
			{ success: true, id: Date.now() },
			{ status: 200 }
		);
	} catch (error) {
		console.error("[Error Reporting Failed]", error);
		return NextResponse.json(
			{ error: "Failed to report error" },
			{ status: 500 }
		);
	}
}
