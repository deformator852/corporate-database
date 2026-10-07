import {api} from "@/shared/lib/api/client";

/** Changes the signed-in user's password; the server then ends every session. */
export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await api.post("/auth/password", {current_password: currentPassword, new_password: newPassword});
}
