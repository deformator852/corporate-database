import {screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import {apiError} from "@/test/api";
import {renderApp, sessionUser} from "@/test/app";

describe("Sign-in", () => {
    it("signs in and opens the workspace", async () => {
        const {user, server, router} = renderApp("/login", null, (s) =>
            s.on("POST", "/auth/login", sessionUser(["documents.list"])),
        );

        await user.type(await screen.findByLabelText("Email"), "marta@acme.io");
        await user.type(screen.getByLabelText("Password"), "Secret-pass-1");
        await user.click(screen.getByRole("button", {name: "Sign in"}));

        expect(await screen.findByRole("navigation")).toBeInTheDocument();
        expect(router.state.location.pathname).toBe("/");
        expect(server.sent("POST", "/auth/login")[0].body).toEqual({email: "marta@acme.io", password: "Secret-pass-1"});
    });

    it("shows the server's reason when sign-in fails", async () => {
        const {user} = renderApp("/login", null, (s) =>
            s.on("POST", "/auth/login", apiError(429, "Too many failed sign-in attempts. Try again in 15 minutes.", "rate_limited")),
        );

        await user.type(await screen.findByLabelText("Email"), "marta@acme.io");
        await user.type(screen.getByLabelText("Password"), "Wrong-pass-1");
        await user.click(screen.getByRole("button", {name: "Sign in"}));

        expect(await screen.findByRole("alert")).toHaveTextContent("Too many failed sign-in attempts");
    });

    it("checks the form before asking the server", async () => {
        const {user, server} = renderApp("/login", null);

        await user.type(await screen.findByLabelText("Email"), "not-an-email");
        await user.type(screen.getByLabelText("Password"), "short");
        await user.click(screen.getByRole("button", {name: "Sign in"}));

        expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
        expect(screen.getByLabelText("Password")).toHaveAttribute("aria-invalid", "true");
        expect(server.sent("POST", "/auth/login")).toHaveLength(0);
    });

    it("leads with the company's sign-in while single sign-on is on", async () => {
        renderApp("/login", null, (s) => s.on("GET", "/auth/methods", {password: false, sso: {name: "Acme"}}));

        expect(await screen.findByRole("link", {name: "Sign in with Acme"})).toBeInTheDocument();
        expect(screen.getByRole("link", {name: "Sign in with Acme"})).toHaveAttribute("href", "/api/v1/auth/sso/start");
        expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
    });

    it("keeps a password sign-in for administrators behind a link", async () => {
        const {user} = renderApp("/login", null, (s) => s.on("GET", "/auth/methods", {password: false, sso: {name: "Acme"}}));

        await user.click(await screen.findByRole("button", {name: "Administrator sign-in with a password"}));
        expect(screen.getByLabelText("Password")).toBeInTheDocument();
        expect(screen.getByRole("link", {name: "Sign in with Acme"})).toBeInTheDocument();
    });

    it("explains why the company's sign-in failed", async () => {
        renderApp("/login?sso_error=sso_account_exists", null, (s) =>
            s.on("GET", "/auth/methods", {password: true, sso: {name: "Acme"}}),
        );
        expect(await screen.findByRole("alert")).toHaveTextContent("An account with your email already exists");
    });

    it("shows a general reason for codes it does not know", async () => {
        renderApp("/login?sso_error=<script>", null);
        expect(await screen.findByRole("alert")).toHaveTextContent("Single sign-on failed");
    });
});
