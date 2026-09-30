import {act, screen, waitFor, within} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import {apiError, reply} from "@/test/api";
import {renderApp, sessionUser} from "@/test/app";
import {FakeWebSocket} from "@/test/socket";

const SAVED = {id: 7, title: "Travel budget?", created_at: "2026-09-30T09:00:00Z", updated_at: "2026-09-30T09:00:00Z"};

async function openChat(script?: Parameters<typeof renderApp>[2]) {
    const view = renderApp("/", sessionUser(["documents.list"]), script);
    const socket = await waitFor(() => FakeWebSocket.at("/api/v1/chat/ws"));
    return {...view, socket};
}

async function ask(user: ReturnType<typeof renderApp>["user"], question: string) {
    await user.type(screen.getByRole("textbox", {name: "Message"}), `${question}{Enter}`);
}

describe("Assistant chat", () => {
    it("streams an answer and lists the documents it used", async () => {
        const {user, socket, server} = await openChat();

        await ask(user, "What is the travel budget?");
        await waitFor(() => expect(socket.sent).toHaveLength(1));
        expect(socket.sent[0]).toEqual({
            type: "ask",
            messages: [{role: "user", content: "What is the travel budget?"}],
            conversation_id: null,
        });
        expect(screen.getByRole("textbox", {name: "Message"})).toHaveValue("");

        act(() => socket.receive({type: "delta", content: "The budget "}));
        expect(await screen.findByText(/The budget/)).toBeInTheDocument();
        server.on("GET", "/chat/conversations", {items: [SAVED], total: 1});
        act(() =>
            socket.receive({
                type: "answer",
                content: "The budget is 500 EUR.",
                conversation_id: 7,
                sources: [{id: 3, name: "Travel policy", filename: "policy.pdf"}],
            }),
        );

        expect(await screen.findByText("The budget is 500 EUR.")).toBeInTheDocument();
        expect(screen.getByRole("button", {name: "Open Travel policy"})).toBeInTheDocument();
        const history = screen.getByRole("complementary", {name: "History"});
        expect(await within(history).findByText("Travel budget?")).toBeInTheDocument();

        await ask(user, "And for trains?");  // the follow-up continues the saved chat
        await waitFor(() => expect(socket.sent).toHaveLength(2));
        expect(socket.sent[1]).toMatchObject({conversation_id: 7});
        expect((socket.sent[1] as {messages: unknown[]}).messages).toHaveLength(3);
    });

    it("keeps what was written when the user stops the answer", async () => {
        const {user, socket} = await openChat();
        await ask(user, "Summarize the handbook");
        act(() => socket.receive({type: "delta", content: "The handbook covers "}));

        await user.click(await screen.findByRole("button", {name: "Stop generating"}));
        expect(socket.sent.at(-1)).toEqual({type: "cancel"});
        act(() => socket.receive({type: "cancelled"}));

        expect(await screen.findByRole("button", {name: "Send"})).toBeInTheDocument();
        expect(screen.getByText("The handbook covers")).toBeInTheDocument();
    });

    it("gives a refused question back instead of losing it", async () => {
        const {user, socket} = await openChat();
        await ask(user, "Question from a second tab");
        act(() =>
            socket.receive({type: "error", code: "busy", message: "Your previous question is still being answered. Wait for it or stop it."}),
        );

        expect(await screen.findByRole("status")).toHaveTextContent("still being answered");
        expect(screen.getByRole("textbox", {name: "Message"})).toHaveValue("Question from a second tab");
        const log = screen.queryByRole("log");
        expect(log === null || !within(log).queryByText("Question from a second tab")).toBe(true);
        expect(screen.queryByRole("button", {name: "Try again"})).not.toBeInTheDocument();
    });

    it("offers a retry when the answer fails", async () => {
        const {user, socket} = await openChat();
        await ask(user, "Hello?");
        act(() => socket.receive({type: "error", code: "unavailable", message: "The chat model is not available."}));

        expect(await screen.findByText("The chat model is not available.")).toBeInTheDocument();
        await user.click(screen.getByRole("button", {name: "Try again"}));
        await waitFor(() => expect(socket.sent).toHaveLength(2));
        expect(socket.sent[1]).toEqual(socket.sent[0]);
    });

    it("opens and deletes saved chats", async () => {
        const {user, server} = await openChat((s) => {
            s.on("GET", "/chat/conversations", {items: [SAVED], total: 1});
            s.on("GET", "/chat/conversations/:id", {
                ...SAVED,
                messages: [
                    {id: 1, role: "user", content: "Travel budget?", sources: [], created_at: SAVED.created_at},
                    {id: 2, role: "assistant", content: "500 EUR per trip.", sources: [], created_at: SAVED.created_at},
                ],
            });
            s.on("DELETE", "/chat/conversations/:id", () => {
                server.on("GET", "/chat/conversations", {items: [], total: 0});
                return {};
            });
        });
        const history = screen.getByRole("complementary", {name: "History"});

        await user.click(await within(history).findByRole("button", {name: /Travel budget\?/}));
        expect(await screen.findByText("500 EUR per trip.")).toBeInTheDocument();

        await user.click(within(history).getByRole("button", {name: "Delete chat"}));
        expect(await within(history).findByText("No saved chats yet")).toBeInTheDocument();
        expect(screen.getByText("Ask about your documents", {selector: "p"})).toBeInTheDocument();
    });

    it("explains when saved chats cannot be loaded", async () => {
        await openChat((s) => s.on("GET", "/chat/conversations", apiError(503, "Service unavailable")));
        const history = screen.getByRole("complementary", {name: "History"});
        expect(await within(history).findByRole("alert")).toHaveTextContent("Service unavailable");
    });

    it("reconnects with a fresh session after the server ends the old one", async () => {
        const {socket, server} = await openChat();
        act(() => socket.close(4401));
        await waitFor(() => expect(server.sent("POST", "/auth/refresh")).toHaveLength(1));
        await waitFor(() => expect(FakeWebSocket.at("/api/v1/chat/ws")).not.toBe(socket));
    });

    it("signs out when the session cannot be renewed", async () => {
        const {socket, router} = await openChat((s) => s.on("POST", "/auth/refresh", reply(401)));
        act(() => socket.close(4401));
        await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    });
});
