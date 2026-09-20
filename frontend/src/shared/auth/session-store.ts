import {create} from "zustand";

import type {SessionUser} from "@/shared/auth/types";

type SessionStore = {
    user: SessionUser | null;
    status: "idle" | "loading" | "ready" | "error";
    error: string | null;
    setUser: (user: SessionUser | null) => void;
    clear: () => void;
    fail: (message: string) => void;
};

export const useSessionStore = create<SessionStore>((set) => ({
    user: null,
    status: "idle",
    error: null,
    setUser: (user) => set({user, status: "ready", error: null}),
    clear: () => set({user: null, status: "ready", error: null}),
    fail: (message) => set({status: "error", error: message}),
}));
