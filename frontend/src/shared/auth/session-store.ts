import {create} from "zustand";

import type {SessionUser} from "@/shared/auth/types";

type SessionStore = {
    user: SessionUser | null;
    status: "idle" | "loading" | "ready" | "error";
    error: string | null;
    /** Shown on the sign-in page once the session ended, e.g. after a password change. */
    notice: string | null;
    setUser: (user: SessionUser | null) => void;
    clear: (notice?: string) => void;
    fail: (message: string) => void;
};

export const useSessionStore = create<SessionStore>((set) => ({
    user: null,
    status: "idle",
    error: null,
    notice: null,
    setUser: (user) => set({user, status: "ready", error: null, notice: null}),
    clear: (notice) => set({user: null, status: "ready", error: null, notice: notice ?? null}),
    fail: (message) => set({status: "error", error: message}),
}));
