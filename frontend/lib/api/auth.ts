import { apiConfig } from "@/config/api";
import { apiClient } from "@/lib/api/client";
import type {
	LoginRequest,
	MessageResponse,
	RegisterRequest,
	TokenResponse,
	User,
	VerificationChallenge,
	ResendVerificationResponse,
} from "@/types";
import { APIRequestError } from "@/lib/api/client";
import { requestQueue } from "@/lib/utils/requestQueue";

export async function login(payload: LoginRequest): Promise<TokenResponse> {
	const body = new URLSearchParams();
	body.set("username", payload.email);
	body.set("password", payload.password);

	try {
		const response = await apiClient.post<TokenResponse>(
			apiConfig.endpoints.login,
			body,
			{
				headers: {
					"Content-Type": "application/x-www-form-urlencoded",
				},
			}
		);
		return response.data;
	} catch (error) {
		if (error instanceof APIRequestError) {
			throw error;
		}
		throw new APIRequestError("Failed to login", {
			errorCode: "LOGIN_FAILED",
		});
	}
}

export async function register(payload: RegisterRequest): Promise<VerificationChallenge> {
	try {
		const response = await apiClient.post<VerificationChallenge>(apiConfig.endpoints.register, payload);
		return response.data;
	} catch (error) {
		if (error instanceof APIRequestError) {
			throw error;
		}
		throw new APIRequestError("Failed to register", {
			errorCode: "REGISTER_FAILED",
		});
	}
}

export async function verifyEmail(email: string, code: string): Promise<TokenResponse> {
	const response = await apiClient.post<TokenResponse>(apiConfig.endpoints.verifyEmail, {
		email,
		code,
	});
	return response.data;
}

export async function resendVerification(email: string): Promise<ResendVerificationResponse> {
	const response = await apiClient.post<ResendVerificationResponse>(
		apiConfig.endpoints.resendVerification,
		{ email }
	);
	return response.data;
}

export async function changeEmail(
	newEmail: string,
	password: string
): Promise<VerificationChallenge> {
	const response = await apiClient.post<VerificationChallenge>(apiConfig.endpoints.changeEmail, {
		new_email: newEmail,
		password,
	});
	return response.data;
}

/** Sends a fresh code to the pending address; the previous code stops working. */
export async function resendEmailChangeCode(): Promise<VerificationChallenge> {
	const response = await apiClient.post<VerificationChallenge>(apiConfig.endpoints.resendEmailChangeCode);
	return response.data;
}

/** Drops an unconfirmed email change; the current address is unaffected. */
export async function cancelEmailChange(): Promise<User> {
	const response = await apiClient.delete<User>(apiConfig.endpoints.changeEmail);
	return response.data;
}

/** Switches the account to the pending address once its emailed code is confirmed. */
export async function confirmEmailChange(code: string): Promise<User> {
	const response = await apiClient.post<User>(apiConfig.endpoints.confirmEmailChange, { code });
	return response.data;
}

export async function getCurrentUser(): Promise<User> {
	try {
		const response = await apiClient.get<User>(apiConfig.endpoints.me);
		return response.data;
	} catch (error) {
		if (error instanceof APIRequestError) {
			throw error;
		}
		throw new APIRequestError("Failed to get current user", {
			errorCode: "GET_USER_FAILED",
		});
	}
}

export async function logout(): Promise<MessageResponse> {
	// Queued offline edits hold this account's content; they must not outlive the session
	// or replay under the next account to sign in on this device
	await requestQueue.clear();
	try {
		const response = await apiClient.post<MessageResponse>(apiConfig.endpoints.logout);
		return response.data;
	} catch (error) {
		if (error instanceof APIRequestError) {
			throw error;
		}
		throw new APIRequestError("Failed to logout", {
			errorCode: "LOGOUT_FAILED",
		});
	}
}
