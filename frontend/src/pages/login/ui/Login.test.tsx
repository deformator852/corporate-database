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
});
