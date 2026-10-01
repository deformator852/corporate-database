import {act, fireEvent, screen, waitFor, within} from "@testing-library/react";
import {describe, expect, it, vi} from "vitest";

import {apiError, type ApiRequest} from "@/test/api";
import {renderApp, sessionUser} from "@/test/app";
import {scrollToEnd} from "@/test/setup";

describe("Pickers load long lists as the user scrolls", () => {
    it("role picker fetches the next page", async () => {
        const role = (i: number) => ({key: `team${i}`, name: `Team ${i}`, permissions: [], protected: false, description: ""});
        const {user} = renderApp("/users", sessionUser(["users.list", "users.create", "roles.list"]), (s) => {
            s.on("GET", "/users", {items: [], page: 1, per_page: 20, total: 0, pages: 0});
            s.on("GET", "/roles", (req: ApiRequest) =>
                Number(req.params.page) === 1
                    ? {items: Array.from({length: 20}, (_, i) => role(i)), page: 1, per_page: 20, total: 21, pages: 2}
                    : {items: [role(20)], page: 2, per_page: 20, total: 21, pages: 2},
            );
        });

        await user.click(await screen.findByRole("button", {name: "Create user"}));
        const dialog = await screen.findByRole("dialog");
        await within(dialog).findByRole("checkbox", {name: "Team 0"});
        act(() => scrollToEnd());
        expect(await within(dialog).findByRole("checkbox", {name: "Team 20"})).toBeInTheDocument();
    });
});

describe("Failures keep the user informed", () => {
    it("a failed delete keeps the dialog open with the reason", async () => {
        const {user} = renderApp("/users", sessionUser(["users.list", "users.delete"]), (s) => {
            s.on("GET", "/users", {items: [{id: 2, first_name: "Ana", last_name: "López", email: "ana@acme.io", roles: [], is_last_admin: true, disabled: false}], page: 1, per_page: 20, total: 1, pages: 1});
            s.on("DELETE", "/users/:id", apiError(409, "The Admin role cannot be removed from the last admin", "conflict"));
        });
        await user.click(await screen.findByRole("button", {name: "Delete Ana López"}));
        const dialog = await screen.findByRole("alertdialog");
        await user.click(within(dialog).getByRole("button", {name: "Delete user"}));
        expect(await within(dialog).findByRole("alert")).toHaveTextContent("last admin");
    });

    it("a file can be dropped onto the upload area", async () => {
        const {user, server} = renderApp("/documents", sessionUser(["documents.list", "documents.create"]), (s) => {
            s.on("GET", "/documents", {items: [], page: 1, per_page: 20, total: 0, pages: 0});
            s.on("POST", "/documents", {id: 1, name: "minutes", filename: "minutes.docx", status: "queued", progress: 0, classification: "standard", error_message: null, created_at: "2026-09-30T10:00:00Z", converted: true});
        });
        const area = (await screen.findByText("Drop a file here or choose one")).parentElement as HTMLElement;
        const file = new File(["old word"], "minutes.doc");
        fireEvent.dragOver(area, {dataTransfer: {files: [file], dropEffect: ""}});
        fireEvent.drop(area, {dataTransfer: {files: [file]}});
        expect(await screen.findByText("minutes.doc")).toBeInTheDocument();
        await user.click(screen.getByRole("button", {name: "Upload"}));
        expect(await screen.findByText(/converted/i)).toBeInTheDocument();
        expect((server.sent("POST", "/documents")[0].body as FormData).get("name")).toBe("minutes");
    });
});

describe("Notifications read state survives closing the tab", () => {
    it("sends pending reads with keepalive when the page is hidden", async () => {
        document.cookie = "csrf_access_token=tok";
        const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, {status: 204}));
        const {user} = renderApp("/", sessionUser(), (s) =>
            s.on("GET", "/notifications", {items: [{id: 8, user_id: 1, type: "document.completed", message: "Ready", read: false, created_at: "2026-09-30T10:00:00Z"}], page: 1, per_page: 20, total: 1, pages: 1, unread_count: 1}),
        );
        await user.click(await screen.findByRole("button", {name: "Notifications, 1 unread"}));
        await screen.findByText("Ready");
        act(() => scrollToEnd());

        act(() => {
            window.dispatchEvent(new Event("pagehide"));
        });

        await waitFor(() => expect(fetch).toHaveBeenCalled());
        const [url, init] = fetch.mock.calls[0] as [string, RequestInit];
        expect(url).toBe("/api/v1/notifications/read");
        expect(init.keepalive).toBe(true);
        expect(JSON.parse(String(init.body))).toEqual({ids: [8]});
        expect(new Headers(init.headers).get("X-CSRF-TOKEN")).toBe("tok");
    });
});

describe("Enabling a user", () => {
    it("shows a failure next to that user's row", async () => {
        const {user} = renderApp("/users", sessionUser(["users.list", "users.disable"]), (s) => {
            s.on("GET", "/users", {items: [{id: 2, first_name: "Ana", last_name: "López", email: "ana@acme.io", roles: [], is_last_admin: false, disabled: true}], page: 1, per_page: 20, total: 1, pages: 1});
            s.on("POST", "/users/:id/enable", apiError(403, "You cannot change an account or role with more access than yours", "forbidden"));
        });
        await user.click(await screen.findByRole("button", {name: "Enable Ana López"}));
        const row = screen.getByText("ana@acme.io").closest("tr") as HTMLElement;
        expect(await within(row).findByRole("alert")).toHaveTextContent("more access than yours");
    });
});
