import {useEffect, useRef, useState} from "react";

import {connectChatSocket, type ChatSocket} from "@pages/home/api/chat";
import {
    ChatCancelledError,
    ChatRequestError,
    type ChatMessage,
    type ChatStatus,
} from "@pages/home/model/chat";
import {ChatComposer} from "@pages/home/ui/ChatComposer";
import {ChatMessages} from "@pages/home/ui/ChatMessages";

function nextId() {
    return crypto.randomUUID();
}

function Home() {
    const socketRef = useRef<ChatSocket | null>(null);
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [draft, setDraft] = useState("");
    const [status, setStatus] = useState<ChatStatus>("idle");
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const socket = connectChatSocket();
        socketRef.current = socket;
        return () => {
            socket.close();
            socketRef.current = null;
        };
    }, []);

    async function send(history: ChatMessage[]) {
        const socket = socketRef.current;
        if (socket == null) {
            setError("Could not send the message.");
            setStatus("error");
            return;
        }
        setStatus("pending");
        setError(null);
        try {
            const content = await socket.send(
                history.map(({role, content}) => ({role, content})),
            );
            setMessages((current) => [
                ...current,
                {id: nextId(), role: "assistant", content},
            ]);
            setStatus("idle");
        } catch (caught) {
            if (caught instanceof ChatCancelledError) {
                setStatus("idle");
                setError(null);
                return;
            }
            const message =
                caught instanceof ChatRequestError
                    ? caught.message
                    : "Could not send the message.";
            setError(message);
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

    function handleCancel() {
        socketRef.current?.cancel();
    }

    function handleRetry() {
        if (status === "pending") {
            return;
        }
        void send(messages);
    }

    return (
        <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden">
            <h1 className="sr-only">Assistant</h1>
            <section
                aria-label="Assistant chat"
                className="flex h-full min-h-0 flex-1 flex-col overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10"
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
                    pending={status === "pending"}
                    onChange={setDraft}
                    onSubmit={handleSubmit}
                    onCancel={handleCancel}
                />
            </section>
        </div>
    );
}

export default Home;
