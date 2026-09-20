import {api} from "@/shared/lib/api/client";
import type {SessionUser} from "@/shared/auth/types";
import type {LoginFormData} from "@pages/login/schema/loginForm";

export async function login(payload: LoginFormData): Promise<SessionUser> {
    const {data} = await api.post<SessionUser>("/auth/login", payload);
    return data;
}
