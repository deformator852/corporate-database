import {screen, waitFor, within} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import type {ApiRequest} from "@/test/api";
import {renderApp, sessionUser} from "@/test/app";

const ANA = {id: 2, name: "Ana López", email: "ana@acme.io"};
const LUIS = {id: 3, name: "Luis Gil", email: "luis@acme.io"};
const CHAT = {id: 7, title: "Travel budget?", created_at: "2026-09-30T09:00:00Z", updated_at: "2026-09-30T09:05:00Z", message_count: 2, user: ANA};

function chats(request: ApiRequest) {
    const all = [CHAT, {...CHAT, id: 8, title: "Leave policy?", user: LUIS}];
    const items = request.params.user_id ? all.filter((chat) => chat.user.id === request.params.user_id) : all;
    return {items, page: 1, per_page: 20, total: items.length, pages: 1};
}

describe("Chat history", () => {
    it("lists every user's chats, narrows to one user and opens a chat read-only", async () => {
        const {user, server} = renderApp("/chat-history", sessionUser(["chat.history"]), (s) => {
            s.on("GET", "/chat/review/conversations", chats);
            s.on("GET", "/chat/review/conversations/:id", {
                id: 7,
                title: "Travel budget?",
                user: ANA,
                messages: [
                    {id: 1, role: "user", content: "Travel budget?", sources: [], created_at: CHAT.created_at, rating: null},
                    {id: 2, role: "assistant", content: "500 EUR per trip.", sources: [], created_at: CHAT.updated_at, rating: "down"},
                ],
            });
        });

        const table = await screen.findByRole("table", {name: "Chat history"});
        expect(within(table).getByText("Leave policy?")).toBeInTheDocument();
        expect(screen.queryByRole("button", {name: "Clear chat history"})).not.toBeInTheDocument();  // no chat.purge

        await user.click(within(table).getByRole("button", {name: "Ana López"}));
        await waitFor(() => expect(within(screen.getByRole("table")).queryByText("Leave policy?")).not.toBeInTheDocument());
        expect(server.sent("GET", "/chat/review/conversations").at(-1)?.params.user_id).toBe(2);

        await user.click(screen.getByRole("link", {name: "Travel budget?"}));
        expect(await screen.findByText("500 EUR per trip.")).toBeInTheDocument();
        expect(screen.getByText("Bad answer")).toBeInTheDocument();
        expect(screen.queryByRole("textbox")).not.toBeInTheDocument();  // nothing to write
        expect(screen.queryByRole("button", {name: "Delete chat"})).not.toBeInTheDocument();  // no chat.purge
    });

    it("deletes one chat from the list after asking", async () => {
        let deleted = false;
        const {user, server} = renderApp("/chat-history", sessionUser(["chat.history", "chat.purge"]), (s) => {
            s.on("GET", "/chat/review/conversations", (request: ApiRequest) => {
                const page = chats(request);
                const items = deleted ? page.items.filter((chat) => chat.id !== 7) : page.items;
                return {...page, items, total: items.length};
            });
            s.on("DELETE", "/chat/review/conversations/:id", () => {
                deleted = true;
                return {};
            });
        });

        const table = await screen.findByRole("table", {name: "Chat history"});
        await user.click(within(table).getByRole("button", {name: "Delete chat Travel budget?"}));
        const dialog = await screen.findByRole("alertdialog");
        expect(dialog).toHaveTextContent("Ana López's chat is deleted with all its messages and answer ratings.");
        await user.click(within(dialog).getByRole("button", {name: "Delete"}));

        await waitFor(() => expect(within(screen.getByRole("table")).queryByText("Travel budget?")).not.toBeInTheDocument());
        expect(server.sent("DELETE", "/chat/review/conversations/7")).toHaveLength(1);
    });

    it("deletes the open chat and goes back to the list", async () => {
        const {user, router} = renderApp("/chat-history", sessionUser(["chat.history", "chat.purge"]), (s) => {
            s.on("GET", "/chat/review/conversations", chats);
            s.on("GET", "/chat/review/conversations/:id", {
                id: 7,
                title: "Travel budget?",
                user: ANA,
                messages: [{id: 1, role: "user", content: "Travel budget?", sources: [], created_at: CHAT.created_at, rating: null}],
            });
            s.on("DELETE", "/chat/review/conversations/:id");
        });

        await user.click(await screen.findByRole("link", {name: "Travel budget?"}));
        await user.click(await screen.findByRole("button", {name: "Delete chat"}));
        await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", {name: "Delete"}));

        await waitFor(() => expect(router.state.location.pathname).toBe("/chat-history"));
    });

    it("clears a chosen date range of chats", async () => {
        const {user, server} = renderApp("/chat-history", sessionUser(["chat.history", "chat.purge"]), (s) => {
            s.on("GET", "/chat/review/conversations", chats);
            s.on("POST", "/chat/review/purge", {deleted: 2});
        });

        await user.click(await screen.findByRole("button", {name: "Clear chat history"}));
        const dialog = await screen.findByRole("alertdialog", {name: "Clear chat history"});
        await user.selectOptions(within(dialog).getByLabelText("Period"), "custom");
        await user.type(within(dialog).getByLabelText("From"), "2026-09-10");
        await user.type(within(dialog).getByLabelText("To"), "2026-09-01");
        await user.click(within(dialog).getByRole("button", {name: "Clear"}));
        expect(await within(dialog).findByText("The start date must not be after the end date.")).toBeInTheDocument();

        await user.clear(within(dialog).getByLabelText("To"));
        await user.type(within(dialog).getByLabelText("To"), "2026-09-20");
        await user.click(within(dialog).getByRole("button", {name: "Clear"}));

        expect(await screen.findByText("Chats deleted: 2.")).toBeInTheDocument();
        const body = server.sent("POST", "/chat/review/purge")[0].body as {since: string; until: string; user_id: null};
        expect(new Date(body.since)).toEqual(new Date(2026, 8, 10));
        expect(new Date(body.until)).toEqual(new Date(2026, 8, 21));  // the end day is included
        expect(body.user_id).toBeNull();
    });
});

describe("User page chat actions", () => {
    const PROFILE = {
        id: 2, first_name: "Ana", last_name: "López", email: "ana@acme.io", disabled: false,
        roles: [], created_at: "2026-01-10T08:00:00Z", last_sign_in_at: null, actions_total: 0,
    };

    it("opens the user's chats and clears their history for a period", async () => {
        const {user, server} = renderApp("/users/2", sessionUser(["users.view", "chat.history", "chat.purge"]), (s) => {
            s.on("GET", "/users/:id", PROFILE);
            s.on("GET", "/users/:id/activity", {items: [], next_cursor: null});
            s.on("POST", "/chat/review/purge", {deleted: 1});
        });

        const view = await screen.findByRole("link", {name: "View chats"});
        expect(view).toHaveAttribute("href", "/chat-history?user=2");
        await user.click(screen.getByRole("button", {name: "Clear chat history"}));
        const dialog = await screen.findByRole("alertdialog", {name: "Clear chat history of Ana López"});
        await user.selectOptions(within(dialog).getByLabelText("Period"), "week");
        await user.click(within(dialog).getByRole("button", {name: "Clear"}));

        expect(await screen.findByText("Chats deleted: 1.")).toBeInTheDocument();
        const body = server.sent("POST", "/chat/review/purge")[0].body as {since: string; until: null; user_id: number};
        expect(body.user_id).toBe(2);
        expect(body.until).toBeNull();
        const days = (Date.now() - new Date(body.since).getTime()) / 86_400_000;
        expect(Math.round(days)).toBe(7);
    });

    it("names the user whose chats are shown even when there are none", async () => {
        const {user} = renderApp("/users/2", sessionUser(["users.view", "chat.history"]), (s) => {
            s.on("GET", "/users/:id", PROFILE);
            s.on("GET", "/users/:id/activity", {items: [], next_cursor: null});
            s.on("GET", "/chat/review/conversations", {items: [], page: 1, per_page: 20, total: 0, pages: 0});
        });

        await user.click(await screen.findByRole("link", {name: "View chats"}));

        expect(await screen.findByText("No saved chats")).toBeInTheDocument();
        expect(screen.getByText("Ana López")).toBeInTheDocument();
    });

    it("hides chat actions without the permissions", async () => {
        renderApp("/users/2", sessionUser(["users.view"]), (s) => {
            s.on("GET", "/users/:id", PROFILE);
            s.on("GET", "/users/:id/activity", {items: [], next_cursor: null});
        });
        expect(await screen.findByRole("heading", {name: "Ana López"})).toBeInTheDocument();
        expect(screen.queryByRole("link", {name: "View chats"})).not.toBeInTheDocument();
        expect(screen.queryByRole("button", {name: "Clear chat history"})).not.toBeInTheDocument();
    });
});
