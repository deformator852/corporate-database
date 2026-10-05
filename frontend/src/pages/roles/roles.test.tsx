import {screen, waitFor, within} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import {apiError, type MockApi} from "@/test/api";
import {renderApp, sessionUser} from "@/test/app";

const MANAGER = ["roles.list", "roles.create", "roles.update", "roles.delete", "permissions.list"];

type Role = {key: string; name: string; description?: string; protected?: boolean; permissions?: {key: string; name: string}[]};

const CATALOG = [
    {key: "documents.list", name: "List documents", description: "", roles: [{key: "legal", name: "Legal"}]},
    {key: "documents.secret", name: "Secret documents", description: "", roles: []},
    {key: "audit.list", name: "View audit log", description: "", roles: []},
];

function roles(server: MockApi, list: Role[]) {
    server.on("GET", "/roles", () => ({
        items: list.map((r) => ({description: "", permissions: [], protected: false, ...r})),
        page: 1, per_page: 20, total: list.length, pages: 1,
    }));
    server.on("GET", "/permissions", (req) => {
        const q = String(req.params.q ?? "").toLowerCase();
        const items = CATALOG.filter((p) => !q || p.name.toLowerCase().includes(q) || p.key.includes(q));
        return {items, page: 1, per_page: 20, total: items.length, pages: 1};
    });
}

const ADMIN: Role = {key: "admin", name: "Admin", protected: true, permissions: [{key: "documents.list", name: "List documents"}]};
const LEGAL: Role = {key: "legal", name: "Legal", permissions: [{key: "documents.list", name: "List documents"}]};

describe("Roles page", () => {
    it("lists roles with their permissions and protects Admin", async () => {
        renderApp("/roles", sessionUser(MANAGER), (s) => roles(s, [ADMIN, LEGAL]));

        const legal = (await screen.findByText("legal")).closest("tr") as HTMLElement;
        expect(within(legal).getByText("List documents")).toBeInTheDocument();
        expect(screen.getByRole("button", {name: "The Admin role cannot be deleted"})).toBeDisabled();
        expect(screen.getByRole("button", {name: "Delete Legal"})).toBeEnabled();
    });

    it("loads more permissions at the end of the picker list", async () => {
        const many = Array.from({length: 12}, (_, i) => ({key: `p.${i}`, name: `Permission ${i}`, description: "", roles: []}));
        const {user} = renderApp("/roles", sessionUser(MANAGER), (s) => {
            roles(s, [ADMIN]);
            s.on("GET", "/permissions", (req) => {
                const page = Number(req.params.page ?? 1);
                return {items: many.slice((page - 1) * 10, page * 10), page, per_page: 10, total: 12, pages: 2};
            });
        });

        await user.click(await screen.findByRole("button", {name: "Create role"}));
        const dialog = await screen.findByRole("dialog");

        // jsdom has no layout: the list counts as scrolled to its end.
        expect(await within(dialog).findByRole("checkbox", {name: "Permission 11"})).toBeInTheDocument();
    });

    it("creates a role: key follows the name, permissions come from a searchable catalog", async () => {
        const {user, server} = renderApp("/roles", sessionUser(MANAGER), (s) => {
            roles(s, [ADMIN]);
            s.on("POST", "/roles", (req) => ({key: "hr.team", permissions: [], protected: false, ...(req.body as object)}));
        });

        await user.click(await screen.findByRole("button", {name: "Create role"}));
        const dialog = await screen.findByRole("dialog");
        await user.type(within(dialog).getByLabelText("Name"), "HR team");
        expect(within(dialog).getByText("hr.team")).toBeInTheDocument();
        await user.type(within(dialog).getByLabelText("Description"), "People operations");
        await within(dialog).findByRole("checkbox", {name: "List documents"});  // catalog loaded
        await user.type(within(dialog).getByRole("searchbox", {name: "Search permissions"}), "audit");
        await waitFor(() => expect(within(dialog).queryByRole("checkbox", {name: "List documents"})).not.toBeInTheDocument());
        await user.click(await within(dialog).findByRole("checkbox", {name: "View audit log"}));
        await user.click(within(dialog).getByRole("button", {name: "Create role"}));

        expect(server.sent("POST", "/roles")[0].body).toEqual({
            name: "HR team", description: "People operations", permission_keys: ["audit.list"],
        });
        await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    });

    it("rejects a name that cannot become a key", async () => {
        const {user, server} = renderApp("/roles", sessionUser(MANAGER), (s) => roles(s, [ADMIN]));
        await user.click(await screen.findByRole("button", {name: "Create role"}));
        const dialog = await screen.findByRole("dialog");
        await user.type(within(dialog).getByLabelText("Name"), "1st line");
        await user.click(within(dialog).getByRole("button", {name: "Create role"}));
        expect(within(dialog).getByLabelText("Name")).toHaveAttribute("aria-invalid", "true");
        expect(server.sent("POST", "/roles")).toHaveLength(0);
    });

    it("edits a role's permissions and shows a conflict from the server", async () => {
        const {user, server} = renderApp("/roles", sessionUser(MANAGER), (s) => {
            roles(s, [ADMIN, LEGAL]);
            s.on("PATCH", "/roles/:key", apiError(403, "You cannot grant permissions you do not have", "forbidden"));
        });

        await user.click(await screen.findByRole("button", {name: "Edit Legal"}));
        const dialog = await screen.findByRole("dialog");
        await user.click(await within(dialog).findByRole("checkbox", {name: "Secret documents"}));
        await user.click(within(dialog).getByRole("button", {name: "Save changes"}));

        expect(await within(dialog).findByText("You cannot grant permissions you do not have")).toBeInTheDocument();
        expect(server.sent("PATCH", "/roles/legal")[0].body).toEqual({
            description: "", permission_keys: ["documents.list", "documents.secret"],
        });
    });

    it("deletes a role after confirmation", async () => {
        const list = [ADMIN, LEGAL];
        const {user} = renderApp("/roles", sessionUser(MANAGER), (s) => {
            roles(s, list);
            s.on("DELETE", "/roles/:key", () => {
                list.pop();
                return {};
            });
        });

        await user.click(await screen.findByRole("button", {name: "Delete Legal"}));
        await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", {name: "Delete role"}));
        await waitFor(() => expect(screen.queryByText("legal")).not.toBeInTheDocument());
    });
});

describe("Permissions page", () => {
    it("shows the catalog with the roles that hold each permission", async () => {
        renderApp("/permissions", sessionUser(["permissions.list"]), (s) => roles(s, []));
        const row = (await screen.findByText("documents.list")).closest("tr") as HTMLElement;
        expect(within(row).getByText("Legal")).toBeInTheDocument();
        expect(screen.getByText("audit.list")).toBeInTheDocument();
    });

    it("explains when the catalog cannot be loaded", async () => {
        const {user} = renderApp("/permissions", sessionUser(["permissions.list"]), (s) =>
            s.on("GET", "/permissions", apiError(503, "Service unavailable", "unavailable")),
        );
        expect(await screen.findByText("Could not load permissions")).toBeInTheDocument();
        expect(screen.getByText("Service unavailable")).toBeInTheDocument();
        await user.click(screen.getByRole("button", {name: "Try again"}));
    });
});
