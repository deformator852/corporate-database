import {act, screen, waitFor, within} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import {apiError, reply, type ApiRequest} from "@/test/api";
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
            document_ids: [],
            replace_message_id: null,
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
                message_id: 12,
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

    it("shows the passage a source was quoted from, with the answer's words marked", async () => {
        const {user, socket, server} = await openChat((s) =>
            s.on("GET", "/documents/:id/chunks/:index", {text: "Section 40. The travel budget per trip is 500 EUR.", page: 3}),
        );
        await ask(user, "What is the travel budget?");
        await waitFor(() => expect(socket.sent).toHaveLength(1));
        act(() =>
            socket.receive({
                type: "answer",
                content: "The budget is 500 EUR per trip.",
                conversation_id: 7,
                message_id: 12,
                sources: [{id: 3, name: "Travel policy", filename: "policy.pdf", chunk: 41}],
            }),
        );

        await user.click(await screen.findByRole("button", {name: "Open Travel policy"}));

        const dialog = await screen.findByRole("dialog", {name: "Travel policy"});
        expect(within(dialog).getByText(/page 3/)).toBeInTheDocument();
        await waitFor(() => expect(dialog.querySelectorAll("mark")).not.toHaveLength(0));
        const marked = [...dialog.querySelectorAll("mark")].map((mark) => mark.textContent);
        expect(marked).toEqual(["budget", "500"]);  // "trip" is too short to carry a fact
        expect(server.sent("GET", "/documents/3/chunks/41")).toHaveLength(1);
        expect(within(dialog).getByRole("button", {name: "Open file"})).toBeInTheDocument();
    });

    it("continues the chat of a stopped first question", async () => {
        const {user, socket} = await openChat();
        await ask(user, "Summarize the handbook");
        await waitFor(() => expect(socket.sent).toHaveLength(1));
        act(() => socket.receive({type: "started", conversation_id: 9}));
        act(() => socket.receive({type: "delta", content: "The handbook covers"}));
        await user.click(await screen.findByRole("button", {name: "Stop generating"}));
        act(() => socket.receive({type: "cancelled"}));
        await screen.findByRole("button", {name: "Send"});

        await ask(user, "And remote work?");
        await waitFor(() => expect(socket.sent.filter((m) => (m as {type: string}).type === "ask")).toHaveLength(2));
        expect(socket.sent.at(-1)).toMatchObject({conversation_id: 9});
    });

    it("rates an answer and takes the rating back", async () => {
        const {user, socket, server} = await openChat((s) => s.on("PUT", "/chat/conversations/:id/messages/:mid/rating"));
        await ask(user, "What is the travel budget?");
        await waitFor(() => expect(socket.sent).toHaveLength(1));
        act(() =>
            socket.receive({type: "answer", content: "The budget is 500 EUR.", conversation_id: 7, message_id: 12, sources: []}),
        );
        const bad = await screen.findByRole("button", {name: "Bad answer"});

        await user.click(bad);
        expect(bad).toHaveAttribute("aria-pressed", "true");
        await user.click(bad);

        await waitFor(() => expect(server.sent("PUT", "/chat/conversations/7/messages/12/rating")).toHaveLength(2));
        const sent = server.sent("PUT", "/chat/conversations/7/messages/12/rating").map((r) => r.body);
        expect(sent).toEqual([{rating: "down"}, {rating: null}]);
        expect(bad).toHaveAttribute("aria-pressed", "false");
    });

    it("copies an answer and regenerates the last one in its place", async () => {
        const {user, socket} = await openChat();
        await ask(user, "What is the travel budget?");
        await waitFor(() => expect(socket.sent).toHaveLength(1));
        act(() =>
            socket.receive({type: "answer", content: "The budget is 500 EUR.", conversation_id: 7, message_id: 12, sources: []}),
        );

        await user.click(await screen.findByRole("button", {name: "Copy answer"}));
        expect(await navigator.clipboard.readText()).toBe("The budget is 500 EUR.");
        expect(screen.getByRole("button", {name: "Copied"})).toBeInTheDocument();

        await user.click(screen.getByRole("button", {name: "Regenerate answer"}));
        await waitFor(() => expect(socket.sent).toHaveLength(2));
        expect(socket.sent[1]).toMatchObject({
            messages: [{role: "user", content: "What is the travel budget?"}],
            conversation_id: 7,
            replace_message_id: 12,
        });
        expect(screen.queryByText("The budget is 500 EUR.")).not.toBeInTheDocument();
        act(() =>
            socket.receive({type: "answer", content: "Trips cost up to 500 EUR.", conversation_id: 7, message_id: 13, sources: []}),
        );
        expect(await screen.findByText("Trips cost up to 500 EUR.")).toBeInTheDocument();
    });

    it("asks only about the documents the user chose", async () => {
        const {user, socket} = await openChat((s) =>
            s.on("GET", "/documents", {
                items: [
                    {id: 3, name: "Trips"},
                    {id: 4, name: "Leave rules"},
                ],
                page: 1,
                per_page: 10,
                total: 2,
                pages: 1,
            }),
        );

        await user.click(screen.getByRole("button", {name: "All documents"}));
        const dialog = await screen.findByRole("dialog", {name: "Answer from these documents"});
        await user.click(await within(dialog).findByRole("checkbox", {name: "Trips"}));
        await user.click(within(dialog).getByRole("button", {name: "Done"}));

        expect(screen.getByRole("button", {name: "Documents: 1"})).toBeInTheDocument();
        await ask(user, "What is the travel budget?");
        await waitFor(() => expect(socket.sent).toHaveLength(1));
        expect(socket.sent[0]).toMatchObject({document_ids: [3]});
        act(() => socket.receive({type: "answer", content: "900 EUR.", conversation_id: 7, message_id: 12, sources: []}));

        await user.click(screen.getByRole("button", {name: "Remove Trips"}));
        expect(screen.getByRole("button", {name: "All documents"})).toBeInTheDocument();
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

    it("continues in a new chat when the saved one was cleared", async () => {
        const {user, socket} = await openChat();
        await ask(user, "What is the travel budget?");
        act(() =>
            socket.receive({type: "answer", content: "500 EUR.", conversation_id: 7, message_id: 12, sources: []}),
        );
        await screen.findByText("500 EUR.");

        await ask(user, "And for trains?");
        await waitFor(() => expect(socket.sent).toHaveLength(2));
        act(() => socket.receive({type: "error", code: "not_found", message: "Conversation not found"}));
        await user.click(await screen.findByRole("button", {name: "Try again"}));

        await waitFor(() => expect(socket.sent).toHaveLength(3));
        expect(socket.sent[2]).toMatchObject({conversation_id: null, replace_message_id: null});
        expect((socket.sent[2] as {messages: unknown[]}).messages).toHaveLength(3);
    });

    it("opens saved chats, which their owner cannot delete", async () => {
        const {user} = await openChat((s) => {
            s.on("GET", "/chat/conversations", {items: [SAVED], total: 1});
            s.on("GET", "/chat/conversations/:id", {
                ...SAVED,
                messages: [
                    {id: 1, role: "user", content: "Travel budget?", sources: [], created_at: SAVED.created_at},
                    {id: 2, role: "assistant", content: "500 EUR per trip.", sources: [], created_at: SAVED.created_at},
                ],
            });
        });
        const history = screen.getByRole("complementary", {name: "History"});

        await user.click(await within(history).findByRole("button", {name: /Travel budget\?/}));
        expect(await screen.findByText("500 EUR per trip.")).toBeInTheDocument();
        expect(within(history).queryByRole("button", {name: /Delete/})).not.toBeInTheDocument();
    });

    it("shows the open chat's title and who wrote each message", async () => {
        const {user} = await openChat((s) => {
            s.on("GET", "/chat/conversations", {items: [SAVED], total: 1});
            s.on("GET", "/chat/conversations/:id", {
                ...SAVED,
                messages: [
                    {id: 1, role: "user", content: "How much per trip?", sources: [], created_at: SAVED.created_at},
                    {id: 2, role: "assistant", content: "500 EUR per trip.", sources: [], created_at: SAVED.created_at},
                ],
            });
        });
        const panel = screen.getByRole("region", {name: "Assistant chat"});
        expect(within(panel).getByText("Assistant")).toBeInTheDocument();

        const history = screen.getByRole("complementary", {name: "History"});
        await user.click(await within(history).findByRole("button", {name: "Travel budget?"}));

        const log = await screen.findByRole("log", {name: "Conversation"});
        expect(await within(log).findByText("How much per trip?")).toBeInTheDocument();
        expect(within(panel).getByText("Travel budget?")).toBeInTheDocument();
        expect(within(log).getByText("You")).toBeInTheDocument();
        expect(within(log).getByText("Assistant")).toBeInTheDocument();
    });

    it("searches the saved chats", async () => {
        const {user, server} = await openChat((s) =>
            s.on("GET", "/chat/conversations", (request: ApiRequest) =>
                request.params.q === "budget" ? {items: [SAVED], total: 1} : request.params.q ? {items: [], total: 0} : {items: [SAVED, {...SAVED, id: 8, title: "Leave policy?"}], total: 2},
            ),
        );
        const history = screen.getByRole("complementary", {name: "History"});
        expect(await within(history).findByText("Leave policy?")).toBeInTheDocument();

        await user.type(within(history).getByRole("searchbox", {name: "Search chats"}), "budget");
        await waitFor(() => expect(within(history).queryByText("Leave policy?")).not.toBeInTheDocument());
        expect(within(history).getByText("Travel budget?")).toBeInTheDocument();

        await user.type(within(history).getByRole("searchbox", {name: "Search chats"}), "xyz");
        expect(await within(history).findByText("No chats match")).toBeInTheDocument();
        expect(server.sent("GET", "/chat/conversations").at(-1)?.params.q).toBe("budgetxyz");
    });

    it("groups saved chats by age like ChatGPT", async () => {
        const today = new Date().toISOString();
        await openChat((s) =>
            s.on("GET", "/chat/conversations", {
                items: [
                    {...SAVED, id: 8, title: "Leave policy?", created_at: today, updated_at: today},
                    {...SAVED, updated_at: "2020-01-01T09:00:00Z"},
                ],
                total: 2,
            }),
        );
        const history = screen.getByRole("complementary", {name: "History"});
        expect(await within(history).findByRole("region", {name: "Today"})).toHaveTextContent("Leave policy?");
        expect(within(history).getByRole("region", {name: "Older"})).toHaveTextContent("Travel budget?");
    });

    it("hides the chat column and remembers it", async () => {
        const {user} = await openChat((s) => s.on("GET", "/chat/conversations", {items: [SAVED], total: 1}));
        await user.click(screen.getByRole("button", {name: "Hide chats"}));

        expect(screen.queryByRole("complementary", {name: "History"})).not.toBeInTheDocument();
        expect(localStorage.getItem("chat-history-shown")).toBe("0");
    });

    it("opens saved chats from a side panel on phones", async () => {
        const {user} = await openChat((s) => {
            s.on("GET", "/chat/conversations", {items: [SAVED], total: 1});
            s.on("GET", "/chat/conversations/:id", {
                ...SAVED,
                messages: [{id: 2, role: "assistant", content: "500 EUR per trip.", sources: [], created_at: SAVED.created_at}],
            });
        });
        await user.click(screen.getByRole("button", {name: "Show chats"}));
        const panel = await screen.findByRole("dialog", {name: "History"});

        await user.click(await within(panel).findByRole("button", {name: "Travel budget?"}));
        expect(await screen.findByText("500 EUR per trip.")).toBeInTheDocument();
        await waitFor(() => expect(screen.queryByRole("dialog", {name: "History"})).not.toBeInTheDocument());
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
