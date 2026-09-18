import {api} from "@/lib/api/client";
import type {LoginFormData} from "@pages/login/schema/schema";

export type LoginResponse = {
    first_name: string;
    last_name: string;
    email: string;
};

export async function login(payload: LoginFormData): Promise<LoginResponse> {
    const {data} = await api.post<LoginResponse>("/auth/auth", payload);
    return data;
}
