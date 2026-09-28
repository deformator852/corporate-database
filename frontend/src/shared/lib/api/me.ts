import {api} from "@/shared/lib/api/client";
import type {SessionUser} from "@/shared/auth/types";
import {useSessionStore} from "@/shared/auth/session-store";

export async function getMe(): Promise<SessionUser> {
    const {data} = await api.get<SessionUser>("/auth/me");
    return data;
}

export async function signOut(): Promise<void> {
    // Revokes both tokens server side; clearing local state happens regardless.
    try {
        await api.post("/auth/logout");
    } finally {
        useSessionStore.getState().clear();
    }
}

export function can(permission: string, user = useSessionStore.getState().user) {
    return user?.permissions.includes(permission) ?? false;
}