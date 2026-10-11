import {screen, waitFor} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import {apiError} from "@/test/api";
import {renderApp, sessionUser} from "@/test/app";

async function fill(user: ReturnType<typeof renderApp>["user"], current: string, next: string, confirm = next) {
    await user.type(screen.getByLabelText("Current password"), current);
    await user.type(screen.getByLabelText("New password"), next);
    await user.type(screen.getByLabelText("Repeat the new password"), confirm);
    await user.click(screen.getByRole("button", {name: "Change password"}));
}

describe("My account", () => {
    it("opens from the name in the header", async () => {
        const {user, router} = renderApp("/", sessionUser());
        await user.click(await screen.findByRole("link", {name: /Marta Ruiz/}));
        expect(router.state.location.pathname).toBe("/account");
    });

    it("checks the new password before sending it", async () => {
        const {user, server} = renderApp("/account", sessionUser());
        await screen.findByRole("heading", {name: "My account"});

        await fill(user, "old-password", "new-password-1", "new-password-2");

        expect(await screen.findByText("The passwords do not match")).toBeInTheDocument();
        expect(server.sent("POST", "/auth/password")).toHaveLength(0);
    });

    it("shows the server's reason and keeps the user signed in", async () => {
        const {user} = renderApp("/account", sessionUser(), (s) =>
            s.on("POST", "/auth/password", apiError(400, "The current password is wrong.")),
        );
        await screen.findByRole("heading", {name: "My account"});

        await fill(user, "wrong-password", "new-password-1");

        expect(await screen.findByRole("alert")).toHaveTextContent("The current password is wrong.");
        expect(screen.getByRole("heading", {name: "My account"})).toBeInTheDocument();
    });

    it("signs the user out and asks for the new password", async () => {
        const {user, server, router} = renderApp("/account", sessionUser(), (s) => s.on("POST", "/auth/password"));
        await screen.findByRole("heading", {name: "My account"});

        await fill(user, "old-password", "new-password-1");

        await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
        expect(await screen.findByRole("status")).toHaveTextContent("Sign in with the new password.");
        expect(server.sent("POST", "/auth/password")[0].body).toEqual({
            current_password: "old-password",
            new_password: "new-password-1",
        });
    });

    it("sends SSO users to their company for the password", async () => {
        renderApp("/account", sessionUser([], {uses_password: false}));
        expect(await screen.findByText("You sign in with your company account. Change your password there.")).toBeInTheDocument();
        expect(screen.queryByLabelText("Current password")).not.toBeInTheDocument();
    });
});
