import { apiConfig } from "@/config/api";
import { apiClient } from "@/lib/api/client";
import type {
	LoginRequest,
	MessageResponse,
	RegisterRequest,
	TokenResponse,
	User,
} from "@/types";

export async function login(payload: LoginRequest): Promise<TokenResponse> {
	const body = new URLSearchParams();
	body.set("username", payload.email);
	body.set("password", payload.password);

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
}

export async function register(payload: RegisterRequest): Promise<User> {
	const response = await apiClient.post<User>(apiConfig.endpoints.register, payload);
	return response.data;
}

export async function refreshToken(refresh_token?: string): Promise<TokenResponse> {
	const response = await apiClient.post<TokenResponse>(apiConfig.endpoints.refresh, {
		refresh_token,
	});
	return response.data;
}

export async function getCurrentUser(): Promise<User> {
	const response = await apiClient.get<User>(apiConfig.endpoints.me);
	return response.data;
}

export async function logout(): Promise<MessageResponse> {
	const response = await apiClient.post<MessageResponse>(apiConfig.endpoints.logout);
	return response.data;
}
