import {screen, waitFor, within} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import {renderApp, sessionUser} from "@/test/app";

const RATED = {
    message_id: 12,
    conversation_id: 7,
    rating: "down",
    question: "What is the travel budget?",
    answer: "I don't know.",
    sources: [{id: 3, name: "Travel policy", filename: "policy.pdf"}],
    rated_at: "2026-10-07T09:00:00Z",
    user: {id: 5, name: "Ana López", email: "ana@acme.io"},
};

describe("Answer ratings", () => {
    it("lists bad answers with their questions and switches to good ones", async () => {
        const {user, server} = renderApp("/feedback", sessionUser(["chat.feedback"]), (s) =>
            s.on("GET", "/chat/feedback", (req) =>
                req.params.rating === "up"
                    ? {items: [], page: 1, per_page: 20, total: 0, pages: 0}
                    : {items: [RATED], page: 1, per_page: 20, total: 1, pages: 1},
            ),
        );

        expect(await screen.findByText("What is the travel budget?")).toBeInTheDocument();
        expect(screen.getByText("I don't know.")).toBeInTheDocument();
        expect(screen.getByText(/Ana López/)).toBeInTheDocument();
        expect(screen.getByRole("button", {name: "Open Travel policy"})).toBeInTheDocument();

        await user.selectOptions(screen.getByRole("combobox", {name: "Show"}), "up");
        expect(await screen.findByText("No answers rated yet")).toBeInTheDocument();
        await waitFor(() => expect(server.sent("GET", "/chat/feedback").at(-1)?.params).toMatchObject({rating: "up"}));
    });

    it("lists every rated answer, each marked good or bad", async () => {
        const good = {...RATED, message_id: 13, rating: "up", answer: "500 EUR a trip."};
        const {user, server} = renderApp("/feedback", sessionUser(["chat.feedback"]), (s) =>
            s.on("GET", "/chat/feedback", (req) =>
                req.params.rating === "all"
                    ? {items: [good, RATED], page: 1, per_page: 20, total: 2, pages: 1}
                    : {items: [RATED], page: 1, per_page: 20, total: 1, pages: 1},
            ),
        );

        await screen.findByText("I don't know.");
        await user.selectOptions(screen.getByRole("combobox", {name: "Show"}), "all");
        expect(await screen.findByText("500 EUR a trip.")).toBeInTheDocument();
        expect(screen.getByRole("img", {name: "Good answer"})).toBeInTheDocument();
        expect(screen.getByRole("img", {name: "Bad answer"})).toBeInTheDocument();
        expect(server.sent("GET", "/chat/feedback").at(-1)?.params).toMatchObject({rating: "all"});
    });

    it("opens the rated answer in its chat and comes back", async () => {
        const scrolled: string[] = [];
        const original = Element.prototype.scrollIntoView;
        Element.prototype.scrollIntoView = function (this: Element) {
            scrolled.push(this.id);
        };
        try {
            const {user, router} = renderApp("/feedback", sessionUser(["chat.feedback", "chat.history"]), (s) => {
                s.on("GET", "/chat/feedback", {items: [RATED], page: 1, per_page: 20, total: 1, pages: 1});
                s.on("GET", "/chat/review/conversations/:id", {
                    id: 7,
                    title: "Travel budget?",
                    user: RATED.user,
                    messages: [
                        {id: 11, role: "user", content: "What is the travel budget?", sources: [], created_at: RATED.rated_at, rating: null},
                        {id: 12, role: "assistant", content: "I don't know.", sources: [], created_at: RATED.rated_at, rating: "down"},
                    ],
                });
            });

            await user.click(await screen.findByRole("link", {name: "Open chat"}));
            expect(await screen.findByRole("heading", {name: "Travel budget?"})).toBeInTheDocument();
            expect(router.state.location.hash).toBe("#message-12");
            await waitFor(() => expect(scrolled).toEqual(["message-12"]));

            await user.click(screen.getByRole("link", {name: "Back"}));
            expect(router.state.location.pathname).toBe("/feedback");
        } finally {
            Element.prototype.scrollIntoView = original;
        }
    });

    it("deletes a rating after asking, leaving the chat", async () => {
        let removed = false;
        const {user, server} = renderApp("/feedback", sessionUser(["chat.feedback"]), (s) => {
            s.on("GET", "/chat/feedback", () =>
                removed
                    ? {items: [], page: 1, per_page: 20, total: 0, pages: 0}
                    : {items: [RATED], page: 1, per_page: 20, total: 1, pages: 1},
            );
            s.on("DELETE", "/chat/feedback/:id", () => {
                removed = true;
                return {};
            });
        });

        await user.click(await screen.findByRole("button", {name: "Delete this rating"}));
        const dialog = await screen.findByRole("alertdialog");
        expect(dialog).toHaveTextContent("The chat and the answer stay.");
        await user.click(within(dialog).getByRole("button", {name: "Delete"}));

        expect(await screen.findByText("No answers rated yet")).toBeInTheDocument();
        expect(server.sent("DELETE", "/chat/feedback/12")).toHaveLength(1);
    });

    it("offers the chat only to those who may read users' chats", async () => {
        renderApp("/feedback", sessionUser(["chat.feedback"]), (s) =>
            s.on("GET", "/chat/feedback", {items: [RATED], page: 1, per_page: 20, total: 1, pages: 1}),
        );
        await screen.findByText("I don't know.");
        expect(screen.queryByRole("link", {name: "Open chat"})).not.toBeInTheDocument();
    });

    it("is not there without the permission", async () => {
        renderApp("/feedback", sessionUser([]), (s) => s.on("GET", "/chat/feedback", {items: [], total: 0}));
        expect(await screen.findByRole("heading", {name: "Page not found"})).toBeInTheDocument();
    });
});
