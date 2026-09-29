import {History, X} from "lucide-react";
import {useCallback, useEffect, useRef, useState} from "react";

import {Button} from "@/components/ui/button";
import {connectChatSocket, type ChatSocket} from "@pages/home/api/chat";
import {deleteConversation, getConversation, listConversations} from "@pages/home/api/history";
import {
    ChatCancelledError,
    ChatRequestError,
    type ChatConversationItem,
    type ChatMessage,
    type ChatStatus,
} from "@pages/home/model/chat";
import {ChatComposer} from "@pages/home/ui/ChatComposer";
import {ChatHistory} from "@pages/home/ui/ChatHistory";
import {ChatMessages} from "@pages/home/ui/ChatMessages";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {getApiErrorMessage} from "@/shared/lib/api/errors";

function nextId() {
    return crypto.randomUUID();
}

function Home() {
    const {t} = useI18n();
    const socketRef = useRef<ChatSocket | null>(null);
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [draft, setDraft] = useState("");
    const [status, setStatus] = useState<ChatStatus>("idle");
    const [error, setError] = useState<string | null>(null);
    // Answer text received so far while it is being generated.
    const [streaming, setStreaming] = useState<string | null>(null);
    // The saved chat on screen; null until the first answer creates one.
    const [conversationId, setConversationId] = useState<number | null>(null);
    const [conversations, setConversations] = useState<ChatConversationItem[] | null>(null);
    const [historyError, setHistoryError] = useState<string | null>(null);
    // Phones: the history is a panel over the chat, opened from its header.
    const [historyOpen, setHistoryOpen] = useState(false);

    const reloadHistory = useCallback(() => {
        void listConversations()
            .then((items) => {
                setConversations(items);
                setHistoryError(null);
            })
            .catch((reason) => setHistoryError(getApiErrorMessage(reason, t("chat.historyLoadError"))));
    }, [t]);

    useEffect(() => {
        reloadHistory();
    }, [reloadHistory]);

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
            setError(t("chat.errorSend"));
            setStatus("error");
            return;
        }
        setStatus("pending");
        setError(null);
        let partial = "";
        const appendAnswer = (content: string, sources: ChatMessage["sources"] = []) =>
            setMessages((current) => [
                ...current,
                {id: nextId(), role: "assistant", content, sources},
            ]);
        try {
            const reply = await socket.send(
                history.map(({role, content}) => ({role, content})),
                conversationId,
                (piece) => {
                    partial += piece;
                    setStreaming(partial);
                },
            );
            appendAnswer(reply.content, reply.sources);
            setConversationId(reply.conversationId);
            reloadHistory();
            setStatus("idle");
        } catch (caught) {
            if (caught instanceof ChatCancelledError) {
                // Keep what was already written before Stop.
                if (partial.trim()) {
                    appendAnswer(partial.trim());
                }
                setStatus("idle");
                setError(null);
                return;
            }
            const message =
                caught instanceof ChatRequestError
                    ? caught.message
                    : t("chat.errorSend");
            setError(message);
            setStatus("error");
        } finally {
            setStreaming(null);
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

    function startNewChat() {
        setMessages([]);
        setConversationId(null);
        setError(null);
        setStatus("idle");
        setHistoryOpen(false);
    }

    async function openConversation(id: number) {
        setHistoryOpen(false);
        try {
            const conversation = await getConversation(id);
            setMessages(
                conversation.messages.map((message) => ({
                    id: String(message.id),
                    role: message.role,
                    content: message.content,
                    sources: message.sources,
                })),
            );
            setConversationId(conversation.id);
            setError(null);
            setStatus("idle");
        } catch (reason) {
            setError(getApiErrorMessage(reason, t("chat.conversationLoadError")));
            setStatus("error");
        }
    }

    async function removeConversation(id: number) {
        try {
            await deleteConversation(id);
            if (id === conversationId) {
                startNewChat();
            }
            reloadHistory();
        } catch (reason) {
            setHistoryError(getApiErrorMessage(reason, t("chat.historyLoadError")));
        }
    }

    const pending = status === "pending";
    const history = (
        <ChatHistory
            conversations={conversations}
            error={historyError}
            activeId={conversationId}
            disabled={pending}
            onNew={startNewChat}
            onOpen={(id) => void openConversation(id)}
            onDelete={(id) => void removeConversation(id)}
        />
    );

    function handleRetry() {
        if (status === "pending") {
            return;
        }
        void send(messages);
    }

    return (
        <div className="flex h-full min-h-0 flex-1 gap-4 overflow-hidden">
            <h1 className="sr-only">{t("chat.title")}</h1>
            <aside
                aria-label={t("chat.history")}
                className="hidden w-64 shrink-0 overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10 md:block"
            >
                {history}
            </aside>
            <section
                aria-label={t("chat.panelLabel")}
                className="relative flex h-full min-h-0 flex-1 flex-col overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10"
            >
                <header className="flex shrink-0 items-center justify-between gap-2 border-b border-border px-4 py-2.5">
                    <p className="truncate text-sm font-medium">{t("chat.title")}</p>
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="md:hidden"
                        aria-expanded={historyOpen}
                        onClick={() => setHistoryOpen(true)}
                    >
                        <History aria-hidden />
                        {t("chat.history")}
                    </Button>
                </header>
                {historyOpen ? (
                    <div className="absolute inset-0 z-20 flex flex-col bg-card md:hidden">
                        <div className="flex justify-end border-b px-2 py-1.5">
                            <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                aria-label={t("common.close")}
                                onClick={() => setHistoryOpen(false)}
                            >
                                <X />
                            </Button>
                        </div>
                        <div className="min-h-0 flex-1">{history}</div>
                    </div>
                ) : null}
                <ChatMessages
                    messages={messages}
                    streaming={streaming}
                    status={status}
                    error={error}
                    onRetry={handleRetry}
                />
                <ChatComposer
                    value={draft}
                    pending={pending}
                    onChange={setDraft}
                    onSubmit={handleSubmit}
                    onCancel={handleCancel}
                />
            </section>
        </div>
    );
}

export default Home;
