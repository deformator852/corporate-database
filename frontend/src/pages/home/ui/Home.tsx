import {useState} from "react";

import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {sendChatMessage} from "@pages/home/api/chat";
import type {ChatMessage, ChatStatus} from "@pages/home/model/chat";
import {ChatComposer} from "@pages/home/ui/ChatComposer";
import {ChatMessages} from "@pages/home/ui/ChatMessages";

function nextId() {
    return crypto.randomUUID();
}

function Home() {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [draft, setDraft] = useState("");
    const [status, setStatus] = useState<ChatStatus>("idle");
    const [error, setError] = useState<string | null>(null);

    async function send(history: ChatMessage[]) {
        setStatus("pending");
        setError(null);
        try {
            const content = await sendChatMessage(
                history.map(({role, content}) => ({role, content})),
            );
            setMessages((current) => [
                ...current,
                {id: nextId(), role: "assistant", content},
            ]);
            setStatus("idle");
        } catch (caught) {
            setError(getApiErrorMessage(caught, "Could not send the message."));
            setStatus("error");
        }
    }

    function handleSubmit() {
        const content = draft.trim();
        if (!content || status === "pending") {
            return;
        }
        const userMessage: ChatMessage = {id: nextId(), role: "user", content};
        const history = [...messages, userMessage];
        setMessages(history);
        setDraft("");
        void send(history);
    }

    function handleRetry() {
        if (status === "pending") {
            return;
        }
        void send(messages);
    }

    return (
        <div className="flex min-h-0 flex-1 flex-col">
            <h1 className="sr-only">Assistant</h1>
            <section
                aria-label="Assistant chat"
                className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10"
            >
                <header className="flex shrink-0 items-center border-b border-border px-4 py-3">
                    <p className="text-sm font-medium">Assistant</p>
                </header>
                <ChatMessages
                    messages={messages}
                    status={status}
                    error={error}
                    onRetry={handleRetry}
                />
                <ChatComposer
                    value={draft}
                    disabled={status === "pending"}
                    onChange={setDraft}
                    onSubmit={handleSubmit}
                />
            </section>
        </div>
    );
}

export default Home;
