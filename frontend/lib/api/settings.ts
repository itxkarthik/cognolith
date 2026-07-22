import { apiClient } from "@/lib/api/client";
import type { UserAISettings } from "@/types";


export async function getUserAISettings(): Promise<UserAISettings> {
  const response = await apiClient.get<UserAISettings>("/users/me/ai-settings");
  return response.data;
}


export async function updateUserAISettings(payload: {
  llm_model?: string;
  rag_diagnostics_enabled?: boolean;
}): Promise<UserAISettings> {
  const response = await apiClient.patch<UserAISettings>("/users/me/ai-settings", {
    ...payload,
  });
  return response.data;
}
