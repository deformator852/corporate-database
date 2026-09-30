import {screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import {apiError} from "@/test/api";
import {renderApp, sessionUser} from "@/test/app";

describe("Session", () => {
    it("sends signed-out visitors to sign-in", async () => {
        const {router} = renderApp("/users", null);
        expect(await screen.findByRole("button", {name: "Sign in"})).toBeInTheDocument();
        expect(router.state.location.pathname).toBe("/login");
    });

    it("sends signed-in users away from the sign-in page", async () => {
        const {router} = renderApp("/login", sessionUser());
        expect(await screen.findByRole("navigation")).toBeInTheDocument();
        expect(router.state.location.pathname).toBe("/");
    });

    it("offers a retry when the server is down, then continues", async () => {
        let down = true;
        const {user} = renderApp("/", sessionUser(), (s) =>
            s.on("GET", "/auth/me", () => (down ? apiError(503, "Service unavailable", "unavailable") : sessionUser())),
        );

        expect(await screen.findByText("Service unavailable")).toBeInTheDocument();
        down = false;
        await user.click(screen.getByRole("button", {name: "Try again"}));
        expect(await screen.findByRole("navigation")).toBeInTheDocument();
    });

    it("shows only the sections the user may open", async () => {
        renderApp("/", sessionUser(["documents.list", "audit.list"]));
        const nav = await screen.findByRole("navigation");
        const links = [...nav.querySelectorAll("a")].map((a) => a.textContent);
        expect(links).toEqual(["Home", "Documents", "Audit log"]);
    });

    it("signs out", async () => {
        const {user, server, router} = renderApp("/", sessionUser(), (s) => s.on("POST", "/auth/logout"));
        await user.click(await screen.findByRole("button", {name: "Sign out"}));
        expect(await screen.findByRole("button", {name: "Sign in"})).toBeInTheDocument();
        expect(server.sent("POST", "/auth/logout")).toHaveLength(1);
        expect(router.state.location.pathname).toBe("/login");
    });
});
