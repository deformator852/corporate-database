import {screen, waitFor, within} from "@testing-library/react";
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

    it("shows Built with Llama while the AI model is a Llama model", async () => {
        renderApp("/", sessionUser([], {built_with_llama: true}));
        expect(await screen.findByText("Built with Llama")).toBeInTheDocument();
    });

    it("does not show Built with Llama with another AI model", async () => {
        renderApp("/", sessionUser([], {built_with_llama: false}));
        await screen.findByRole("navigation");
        expect(screen.queryByText("Built with Llama")).not.toBeInTheDocument();
    });

    it("signs out", async () => {
        const {user, server, router} = renderApp("/", sessionUser(), (s) => s.on("POST", "/auth/logout"));
        await user.click(await screen.findByRole("button", {name: "Sign out"}));
        expect(await screen.findByRole("button", {name: "Sign in"})).toBeInTheDocument();
        expect(server.sent("POST", "/auth/logout")).toHaveLength(1);
        expect(router.state.location.pathname).toBe("/login");
    });
});

describe("Pages need their permission", () => {
    it("shows not-found instead of a page the user may not open, without calling its API", async () => {
        const {server} = renderApp("/users", sessionUser(["documents.list"]));
        expect(await screen.findByRole("heading", {name: "Page not found"})).toBeInTheDocument();
        expect(server.sent("GET", "/users")).toHaveLength(0);
    });
});

describe("Phone menu", () => {
    it("opens from the header, lists the allowed sections and closes after choosing one", async () => {
        const {user, router} = renderApp("/", sessionUser(["documents.list"]), (s) =>
            s.on("GET", "/documents", {items: [], page: 1, per_page: 20, total: 0, pages: 0}),
        );

        await user.click(await screen.findByRole("button", {name: "Open menu"}));
        const menu = await screen.findByRole("dialog", {name: "Navigation"});
        expect([...menu.querySelectorAll("a")].map((a) => a.textContent)).toEqual(["Home", "Documents"]);

        await user.click(within(menu).getByRole("link", {name: "Documents"}));

        expect(router.state.location.pathname).toBe("/documents");
        await waitFor(() => expect(screen.queryByRole("dialog", {name: "Navigation"})).not.toBeInTheDocument());
    });
});
