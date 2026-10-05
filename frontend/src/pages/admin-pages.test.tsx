import {act, screen, waitFor, within} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import {apiError, type ApiRequest} from "@/test/api";
import {renderApp, sessionUser} from "@/test/app";
import {scrollToEnd} from "@/test/setup";
import {FakeWebSocket} from "@/test/socket";

const ENTRY = {
    id: 1,
    created_at: "2026-09-30T10:00:00Z",
    actor_id: 2,
    actor_email: "ana@acme.io",
    action: "users.update",
    target_type: "user",
    target_id: "3",
    target_label: "luis@acme.io",
    details: {roles: ["legal"], password_changed: true},
    ip: "10.0.0.7",
};

describe("Audit log", () => {
    it("shows who did what, filters by action and search, and links to the user", async () => {
        const {user, server, router} = renderApp("/audit", sessionUser(["audit.list", "users.view"]), (s) =>
            s.on("GET", "/audit", (req: ApiRequest) => ({
                items: req.params.action === "auth.login" ? [] : [ENTRY], page: 1, per_page: 25,
                total: req.params.action === "auth.login" ? 0 : 1, pages: 1,
            })),
        );

        const row = (await screen.findByText("luis@acme.io")).closest("tr") as HTMLElement;
        expect(within(row).getByText("Updated user")).toBeInTheDocument();
        expect(within(row).getByText("password changed · Roles: legal")).toBeInTheDocument();
        expect(within(row).getByText("10.0.0.7")).toBeInTheDocument();

        await user.selectOptions(screen.getByLabelText("Action"), "auth.login");
        expect(await screen.findByText("No entries match")).toBeInTheDocument();
        await user.selectOptions(screen.getByLabelText("Action"), "");
        await user.type(screen.getByLabelText("Search by user, target or IP"), "ana");
        await waitFor(() => expect(server.sent("GET", "/audit").at(-1)?.params.q).toBe("ana"));
        expect(router.state.location.search).toContain("q=ana");

        await user.click(await screen.findByRole("link", {name: "Open ana@acme.io"}));
        expect(router.state.location.pathname).toBe("/users/2");
    });
});

/** A paragraph whose whole text (across nested elements) is `text`. */
function paragraph(text: string) {
    return (_: string, element: Element | null) => element?.tagName === "P" && element.textContent === text;
}

describe("User page", () => {
    const PROFILE = {
        id: 2, first_name: "Ana", last_name: "López", email: "ana@acme.io", disabled: true,
        roles: [{key: "legal", name: "Legal"}], created_at: "2026-01-10T08:00:00Z",
        last_sign_in_at: null, actions_total: 31,
    };

    it("shows the profile and loads older activity while scrolling", async () => {
        const {server} = renderApp("/users/2", sessionUser(["users.view"]), (s) => {
            s.on("GET", "/users/:id", PROFILE);
            s.on("GET", "/users/:id/activity", (req: ApiRequest) =>
                req.params.before
                    ? {items: [{...ENTRY, id: 1, action: "auth.login"}], next_cursor: null}
                    : {items: [{...ENTRY, id: 2}], next_cursor: 2},
            );
        });

        expect(await screen.findByRole("heading", {name: "Ana López"})).toBeInTheDocument();
        expect(screen.getByText("Disabled")).toBeInTheDocument();
        expect(screen.getByText("Legal")).toBeInTheDocument();
        expect(screen.getByText("Never")).toBeInTheDocument();
        act(() => scrollToEnd());  // the list end is on screen at first
        expect(await screen.findByText(paragraph("Updated user · luis@acme.io"))).toBeInTheDocument();

        act(() => scrollToEnd());

        expect(await screen.findByText(paragraph("Signed in · luis@acme.io"))).toBeInTheDocument();
        expect(await screen.findByText("This is the first recorded action.")).toBeInTheDocument();
        expect(server.sent("GET", "/users/2/activity")[1].params.before).toBe(2);
    });

    it("says so when the user no longer exists", async () => {
        renderApp("/users/99", sessionUser(["users.view"]), (s) => {
            s.on("GET", "/users/:id", apiError(404, "User not found", "not_found"));
            s.on("GET", "/users/:id/activity", apiError(404, "User not found", "not_found"));
        });
        expect(await screen.findByText("This user no longer exists")).toBeInTheDocument();
    });
});

describe("System status", () => {
    it("summarizes which components need attention", async () => {
        const {user, server} = renderApp("/system", sessionUser(["system.view"]), (s) =>
            s.on("GET", "/system/status", {
                services: [
                    {name: "database", status: "ok", detail: ""},
                    {name: "llm", status: "down", detail: "Model llama3.1:8b is not downloaded in Ollama."},
                    {name: "embedding", status: "warning", detail: "not loaded yet"},
                ],
                documents: {completed: 12, failed: 1},
                config: {language: "en", llm_model: "llama3.1:8b", llm_context: 16384, embedding_model: "intfloat/multilingual-e5-base", chunk_size: 800, chunk_overlap: 150, text_cleanup: "llm"},
            }),
        );

        expect(await screen.findByText("2 component(s) need attention.")).toBeInTheDocument();
        const llm = screen.getByText("Assistant model").closest("div") as HTMLElement;
        expect(within(llm).getByText("Down")).toBeInTheDocument();
        expect(screen.getByText("Model llama3.1:8b is not downloaded in Ollama.")).toBeInTheDocument();
        expect(screen.getByText("800 / 150")).toBeInTheDocument();

        await user.click(screen.getByRole("button", {name: "Refresh"}));
        await waitFor(() => expect(server.sent("GET", "/system/status")).toHaveLength(2));
    });

    it("explains when the status cannot be loaded", async () => {
        renderApp("/system", sessionUser(["system.view"]), (s) => s.on("GET", "/system/status", apiError(403, "Insufficient permissions", "forbidden")));
        expect(await screen.findByText("Insufficient permissions")).toBeInTheDocument();
    });
});

describe("Notifications", () => {
    const NOTE = {id: 5, user_id: 1, type: "document.completed", message: '"Travel policy" is ready.', read: false, created_at: "2026-09-30T10:00:00Z"};

    function page(items: unknown[], unread: number) {
        return {items, page: 1, per_page: 20, total: items.length, pages: 1, unread_count: unread};
    }

    it("shows one notice for a batch of ready documents", async () => {
        const {user} = renderApp("/", sessionUser(), (s) =>
            s.on("GET", "/notifications", page([{...NOTE, type: "documents.completed", message: "12 documents are ready."}], 1)),
        );
        await user.click(await screen.findByRole("button", {name: "Notifications, 1 unread"}));
        const panel = await screen.findByRole("dialog", {name: "Notifications"});
        expect(within(panel).getByText("Documents ready")).toBeInTheDocument();
        expect(within(panel).getByText("12 documents are ready.")).toBeInTheDocument();
    });

    it("counts unread items, marks them read once seen, and dismisses one", async () => {
        const {user, server} = renderApp("/", sessionUser(), (s) => {
            s.on("GET", "/notifications", page([NOTE, {...NOTE, id: 4, message: "Older", read: true}], 1));
            s.on("POST", "/notifications/read");
            s.on("DELETE", "/notifications/:id");
        });

        const bell = await screen.findByRole("button", {name: "Notifications, 1 unread"});
        await user.click(bell);
        const panel = await screen.findByRole("dialog", {name: "Notifications"});
        expect(within(panel).getByText('"Travel policy" is ready.')).toBeInTheDocument();
        expect(within(panel).getByText("New")).toBeInTheDocument();

        act(() => scrollToEnd());
        await waitFor(() => expect(server.sent("POST", "/notifications/read")[0]?.body).toEqual({ids: [5]}), {timeout: 3000});

        await user.click(within(panel).getAllByRole("button", {name: "Dismiss notification"})[1]);
        await waitFor(() => expect(within(panel).queryByText("Older")).not.toBeInTheDocument());
        expect(server.sent("DELETE", "/notifications/4")).toHaveLength(1);
    });

    it("shows a notification the moment it arrives", async () => {
        renderApp("/", sessionUser());
        await screen.findByRole("button", {name: "Notifications"});
        const socket = await waitFor(() => FakeWebSocket.at("/api/v1/notifications/ws"));

        act(() => socket.receive(NOTE));

        expect(await screen.findByRole("button", {name: "Notifications, 1 unread"})).toBeInTheDocument();
    });

    it("clears all", async () => {
        const {user, server} = renderApp("/", sessionUser(), (s) => {
            s.on("GET", "/notifications", page([NOTE], 1));
            s.on("DELETE", "/notifications");
        });
        await user.click(await screen.findByRole("button", {name: "Notifications, 1 unread"}));
        await user.click(await screen.findByRole("button", {name: "Clear all"}));
        expect(await screen.findByText("You're all caught up")).toBeInTheDocument();
        expect(server.sent("DELETE", "/notifications")).toHaveLength(1);
    });
});
