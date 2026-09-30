import {screen, waitFor, within} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import {apiError, type MockApi} from "@/test/api";
import {renderApp, sessionUser} from "@/test/app";

const MANAGER = ["users.list", "users.view", "users.create", "users.update", "users.delete", "users.disable", "roles.list"];

type Person = {id: number; first_name: string; last_name: string; email: string; disabled?: boolean; roles?: {key: string; name: string}[]};

function people(server: MockApi, list: Person[]) {
    const items = () =>
        list.map((p) => ({roles: [], is_last_admin: false, disabled: false, ...p}));
    server.on("GET", "/users", (req) => {
        const perPage = Number(req.params.per_page);
        const page = Number(req.params.page);
        return {items: items().slice((page - 1) * perPage, page * perPage), page, per_page: perPage, total: list.length, pages: Math.ceil(list.length / perPage)};
    });
    server.on("GET", "/roles", {items: [{key: "admin", name: "Admin", permissions: []}, {key: "legal", name: "Legal", permissions: []}], page: 1, per_page: 20, total: 2, pages: 1});
}

const ANA: Person = {id: 2, first_name: "Ana", last_name: "López", email: "ana@acme.io", roles: [{key: "legal", name: "Legal"}]};
const SELF: Person = {id: 1, first_name: "Marta", last_name: "Ruiz", email: "marta@acme.io"};

function row(name: string): HTMLElement {
    return screen.getByRole("link", {name: `Open ${name}`}).closest("tr") as HTMLElement;
}

describe("Users page", () => {
    it("lists people with their roles and state", async () => {
        renderApp("/users", sessionUser(MANAGER), (s) => people(s, [SELF, {...ANA, disabled: true}]));

        await screen.findByText("ana@acme.io");
        expect(within(row("Ana López")).getByText("Legal")).toBeInTheDocument();
        expect(within(row("Ana López")).getByText("Disabled")).toBeInTheDocument();
        expect(within(row("Marta Ruiz")).queryByText("Disabled")).not.toBeInTheDocument();
    });

    it("creates a user with a role", async () => {
        const {user, server} = renderApp("/users", sessionUser(MANAGER), (s) => {
            people(s, [SELF]);
            s.on("POST", "/users", (req) => ({id: 5, ...(req.body as object), roles: [], is_last_admin: false, disabled: false}));
        });

        await user.click(await screen.findByRole("button", {name: "Create user"}));
        const dialog = await screen.findByRole("dialog");
        await user.type(within(dialog).getByLabelText("First name"), "Luis");
        await user.type(within(dialog).getByLabelText("Last name"), "Pérez");
        await user.type(within(dialog).getByLabelText("Email"), "luis@acme.io");
        await user.type(within(dialog).getByLabelText("Password"), "Welcome-2026");
        await user.click(await within(dialog).findByRole("checkbox", {name: "Legal"}));
        await user.click(within(dialog).getByRole("button", {name: "Create user"}));

        expect(server.sent("POST", "/users")[0].body).toEqual({
            first_name: "Luis", last_name: "Pérez", email: "luis@acme.io", role_keys: ["legal"], password: "Welcome-2026",
        });
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("keeps the form open with the server's reason when saving fails", async () => {
        const {user} = renderApp("/users", sessionUser(MANAGER), (s) => {
            people(s, [SELF]);
            s.on("POST", "/users", apiError(409, "A user with this email already exists", "conflict"));
        });

        await user.click(await screen.findByRole("button", {name: "Create user"}));
        const dialog = await screen.findByRole("dialog");
        await user.type(within(dialog).getByLabelText("First name"), "Luis");
        await user.type(within(dialog).getByLabelText("Last name"), "Pérez");
        await user.type(within(dialog).getByLabelText("Email"), "ana@acme.io");
        await user.type(within(dialog).getByLabelText("Password"), "Welcome-2026");
        await user.click(within(dialog).getByRole("button", {name: "Create user"}));

        expect(await within(dialog).findByText("A user with this email already exists")).toBeInTheDocument();
    });

    it("edits a user without changing the password when it is left empty", async () => {
        const {user, server} = renderApp("/users", sessionUser(MANAGER), (s) => {
            people(s, [SELF, ANA]);
            s.on("PATCH", "/users/:id", (req) => ({...ANA, ...(req.body as object), is_last_admin: false, disabled: false}));
        });

        await user.click(await screen.findByRole("button", {name: "Edit Ana López"}));
        const dialog = await screen.findByRole("dialog");
        const firstName = within(dialog).getByLabelText("First name");
        await user.clear(firstName);
        await user.type(firstName, "Anabel");
        await user.click(within(dialog).getByRole("button", {name: "Save changes"}));

        const [patch] = server.sent("PATCH", "/users/2");
        expect(patch.body).toEqual({first_name: "Anabel", last_name: "López", email: "ana@acme.io", role_keys: ["legal"]});
    });

    it("disables a user after confirmation and enables them again", async () => {
        const list: Person[] = [SELF, ANA];
        const {user, server} = renderApp("/users", sessionUser(MANAGER), (s) => {
            people(s, list);
            s.on("POST", "/users/:id/disable", () => {
                list[1] = {...ANA, disabled: true};
                return {};
            });
            s.on("POST", "/users/:id/enable", () => {
                list[1] = {...ANA, disabled: false};
                return {};
            });
        });

        await user.click(await screen.findByRole("button", {name: "Disable Ana López"}));
        const dialog = await screen.findByRole("alertdialog");
        expect(dialog).toHaveTextContent("activity history stay");
        await user.click(within(dialog).getByRole("button", {name: "Disable user"}));
        expect(await within(row("Ana López")).findByText("Disabled")).toBeInTheDocument();

        await user.click(screen.getByRole("button", {name: "Enable Ana López"}));
        expect(await screen.findByRole("button", {name: "Disable Ana López"})).toBeInTheDocument();
        expect(server.sent("POST", "/users/2/disable")).toHaveLength(1);
        expect(server.sent("POST", "/users/2/enable")).toHaveLength(1);
    });

    it("never offers to disable or delete your own account", async () => {
        renderApp("/users", sessionUser(MANAGER), (s) => people(s, [SELF, ANA]));
        await screen.findByText("ana@acme.io");
        expect(within(row("Marta Ruiz")).getByRole("button", {name: "You cannot disable your own account"})).toBeDisabled();
        expect(within(row("Marta Ruiz")).getByRole("button", {name: "You cannot delete your own account"})).toBeDisabled();
    });

    it("deletes a user after confirmation", async () => {
        const list: Person[] = [SELF, ANA];
        const {user} = renderApp("/users", sessionUser(MANAGER), (s) => {
            people(s, list);
            s.on("DELETE", "/users/:id", () => {
                list.pop();
                return {};
            });
        });

        await user.click(await screen.findByRole("button", {name: "Delete Ana López"}));
        await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", {name: "Delete user"}));
        await waitFor(() => expect(screen.queryByText("ana@acme.io")).not.toBeInTheDocument());
    });

    it("pages through a long list", async () => {
        const many = Array.from({length: 25}, (_, i) => ({id: i + 10, first_name: `User${i}`, last_name: "Test", email: `u${i}@acme.io`}));
        const {user, router} = renderApp("/users", sessionUser(MANAGER), (s) => people(s, many));

        await screen.findByText("u0@acme.io");
        await user.click(screen.getByRole("button", {name: "Next"}));
        expect(await screen.findByText("u24@acme.io")).toBeInTheDocument();
        expect(router.state.location.search).toBe("?page=2");
        expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
    });

    it("hides actions the user may not take", async () => {
        renderApp("/users", sessionUser(["users.list"]), (s) => people(s, [SELF, ANA]));
        await screen.findByText("ana@acme.io");
        expect(screen.queryByRole("button", {name: "Create user"})).not.toBeInTheDocument();
        expect(screen.queryByRole("columnheader", {name: "Actions"})).not.toBeInTheDocument();
        expect(screen.queryByRole("link", {name: "Open Ana López"})).not.toBeInTheDocument();
    });
});
