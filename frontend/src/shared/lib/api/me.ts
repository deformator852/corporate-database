import {api} from "@/shared/lib/api/client";
import type {SessionUser} from "@/shared/auth/types";

export async function getMe(): Promise<SessionUser> {
    const {data} = await api.get<SessionUser>("/auth/me");
    return data;
}
