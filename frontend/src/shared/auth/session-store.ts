import {create} from "zustand";

import type {SessionUser} from "@/shared/auth/types";

type SessionStore = {
    user: SessionUser | null;
    status: "idle" | "loading" | "ready";
    setUser: (user: SessionUser | null) => void;
    clear: () => void;
};

export const useSessionStore = create<SessionStore>((set) => ({
    user: null,
    status: "idle",
    setUser: (user) => set({user, status: "ready"}),
    clear: () => set({user: null, status: "ready"}),
}));
