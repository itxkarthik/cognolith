import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/lib/api/client";

import { cancelEmailChange, changeEmail, confirmEmailChange, resendEmailChangeCode } from "../auth";

vi.mock("@/lib/api/client", () => ({
  APIRequestError: class extends Error {},
  apiClient: {
    delete: vi.fn(),
    post: vi.fn(),
  },
}));

describe("email change API", () => {
  beforeEach(() => {
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.delete).mockReset();
  });

  it("resends a code to the pending address", async () => {
    const challenge = {
      masked_email: "ne***@example.com",
      expires_at: "2026-11-26T10:20:00Z",
      resend_available_at: "2026-11-26T10:11:00Z",
    };
    vi.mocked(apiClient.post).mockResolvedValue({ data: challenge });

    await expect(resendEmailChangeCode()).resolves.toEqual(challenge);
    expect(apiClient.post).toHaveBeenCalledWith("/users/me/email-change/resend");
  });

  it("cancels a pending change", async () => {
    const user = { id: 1, email: "old@example.com", is_active: true, is_superuser: false, is_verified: true, pending_email: null };
    vi.mocked(apiClient.delete).mockResolvedValue({ data: user });

    await expect(cancelEmailChange()).resolves.toEqual(user);
    expect(apiClient.delete).toHaveBeenCalledWith("/users/me/email-change");
  });

  it("requests a code for the new address", async () => {
    const challenge = {
      masked_email: "ne***@example.com",
      expires_at: "2026-11-26T10:10:00Z",
      resend_available_at: "2026-11-26T10:01:00Z",
    };
    vi.mocked(apiClient.post).mockResolvedValue({ data: challenge });

    await expect(changeEmail("new@example.com", "secure-password")).resolves.toEqual(challenge);
    expect(apiClient.post).toHaveBeenCalledWith("/users/me/email-change", {
      new_email: "new@example.com",
      password: "secure-password",
    });
  });

  it("confirms the code and returns the updated user", async () => {
    const user = { id: 1, email: "new@example.com", is_active: true, is_superuser: false, is_verified: true };
    vi.mocked(apiClient.post).mockResolvedValue({ data: user });

    await expect(confirmEmailChange("123456")).resolves.toEqual(user);
    expect(apiClient.post).toHaveBeenCalledWith("/users/me/email-change/confirm", {
      code: "123456",
    });
  });
});
