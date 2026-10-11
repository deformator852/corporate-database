import {describe, expect, it} from "vitest";

import {useSessionStore} from "@/shared/auth/session-store";
import {api, refreshSession} from "@/shared/lib/api/client";
import {getApiErrorCode, getApiErrorMessage} from "@/shared/lib/api/errors";
import {apiError, mockApi, reply} from "@/test/api";
import {sessionUser} from "@/test/app";

describe("API client", () => {
    it("sends the CSRF token on changes, never on reads", async () => {
        document.cookie = "csrf_access_token=abc";
        document.cookie = "csrf_refresh_token=xyz";
        const server = mockApi().on("GET", "/users", []).on("DELETE", "/users/:id").on("POST", "/auth/refresh");

        await api.get("/users");
        await api.delete("/users/3");
        await api.post("/auth/refresh");

        expect(server.calls[0].headers["X-CSRF-TOKEN"]).toBeUndefined();
        expect(server.calls[1].headers["X-CSRF-TOKEN"]).toBe("abc");
        expect(server.calls[2].headers["X-CSRF-TOKEN"]).toBe("xyz");
    });

    it("refreshes an expired session once and repeats the requests", async () => {
        let expired = true;
        const server = mockApi()
            .on("GET", "/users", () => (expired ? reply(401) : ["ana"]))
            .on("GET", "/roles", () => (expired ? reply(401) : ["admin"]))
            .on("POST", "/auth/refresh", () => {
                expired = false;
                return {};
            });

        const [users, roles] = await Promise.all([api.get("/users"), api.get("/roles")]);

        expect(users.data).toEqual(["ana"]);
        expect(roles.data).toEqual(["admin"]);
        expect(server.sent("POST", "/auth/refresh")).toHaveLength(1);
    });

    it("signs the user out when the session cannot be refreshed", async () => {
        useSessionStore.getState().setUser(sessionUser());
        mockApi().on("GET", "/users", reply(401)).on("POST", "/auth/refresh", reply(401));

        await expect(api.get("/users")).rejects.toThrow();
        expect(useSessionStore.getState().user).toBeNull();
    });

    it("does not retry a failed sign-in", async () => {
        const server = mockApi().on("POST", "/auth/login", apiError(401, "Email or password is wrong"));
        await expect(api.post("/auth/login", {})).rejects.toThrow();
        expect(server.sent("POST", "/auth/refresh")).toHaveLength(0);
    });

    it("reads the server's message and code from errors", async () => {
        mockApi().on("GET", "/x", apiError(409, "Role exists", "conflict"));
        const error = await api.get("/x").catch((e: unknown) => e);
        expect(getApiErrorMessage(error, "fallback")).toBe("Role exists");
        expect(getApiErrorCode(error)).toBe("conflict");
        expect(getApiErrorMessage(new Error("boom"), "fallback")).toBe("fallback");
    });

    it("refreshes one tab at a time, so tabs never spend the same refresh token", async () => {
        const held: string[] = [];
        let queue = Promise.resolve();
        const locks = {
            // Like the browser's: one holder of a name at a time, in order.
            request: (name: string, work: () => Promise<unknown>) => {
                const run = queue.then(async () => {
                    held.push(name);
                    return work();
                });
                queue = run.then(() => undefined, () => undefined);
                return run;
            },
        };
        Object.defineProperty(navigator, "locks", {value: locks, configurable: true});
        try {
            mockApi().on("POST", "/auth/refresh");
            await refreshSession();
            expect(held).toEqual(["corpus-session-refresh"]);
        } finally {
            Reflect.deleteProperty(navigator, "locks");
        }
    });
});
