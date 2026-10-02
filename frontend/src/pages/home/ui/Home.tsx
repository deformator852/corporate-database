import {PanelLeft, SquarePen, X} from "lucide-react";
import {useCallback, useEffect, useRef, useState} from "react";

import {Button} from "@/components/ui/button";
import {Sheet, SheetClose, SheetContent, SheetTitle, SheetTrigger} from "@/components/ui/sheet";
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

/** Chat limits (backend services/chat_limit.py): the question was refused
 * before it was saved or answered. */
const NOT_ACCEPTED = new Set(["busy", "rate_limited"]);

/** Remembers whether the desktop history column is shown. */
const HISTORY_SHOWN_KEY = "chat-history-shown";

function readHistoryShown() {
    try {
        return localStorage.getItem(HISTORY_SHOWN_KEY) !== "0";
    } catch {
        return true;
    }
}

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
    // Desktop: a column that can be hidden. Phones: a panel sliding in from the left.
    const [historyShown, setHistoryShown] = useState(readHistoryShown);
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
            if (caught instanceof ChatRequestError && NOT_ACCEPTED.has(caught.code)) {
                // The server did not take the question (limit, another tab
                // still answering): give it back to send later.
                const question = history[history.length - 1];
                setMessages((current) => current.filter((item) => item.id !== question.id));
                setDraft(question.content);
                setError(caught.message);
                setStatus("refused");
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

    function toggleHistory() {
        const next = !historyShown;
        setHistoryShown(next);
        try {
            localStorage.setItem(HISTORY_SHOWN_KEY, next ? "1" : "0");
        } catch {
            // Storage is blocked: the choice lasts until reload.
        }
    }

    function handleRetry() {
        if (status === "pending") {
            return;
        }
        void send(messages);
    }

    return (
        <div className="flex h-full min-h-0 flex-1 gap-4 overflow-hidden">
            <h1 className="sr-only">{t("chat.title")}</h1>
            {historyShown ? (
                <aside
                    id="chat-history"
                    aria-label={t("chat.history")}
                    className="hidden w-64 shrink-0 overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10 md:block"
                >
                    {history}
                </aside>
            ) : null}
            <section
                aria-label={t("chat.panelLabel")}
                className="relative flex h-full min-h-0 flex-1 flex-col overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10"
            >
                <header className="flex shrink-0 items-center gap-1 border-b border-border px-2 py-1.5">
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="hidden md:inline-flex"
                        aria-label={t(historyShown ? "chat.hideHistory" : "chat.showHistory")}
                        aria-controls="chat-history"
                        aria-expanded={historyShown}
                        onClick={toggleHistory}
                    >
                        <PanelLeft aria-hidden />
                    </Button>
                    <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
                        <SheetTrigger
                            render={
                                <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon"
                                    className="md:hidden"
                                    aria-label={t("chat.showHistory")}
                                />
                            }
                        >
                            <PanelLeft aria-hidden />
                        </SheetTrigger>
                        <SheetContent side="left" showCloseButton={false} className="gap-0 p-0">
                            <div className="flex items-center justify-between border-b px-4 py-2">
                                <SheetTitle>{t("chat.history")}</SheetTitle>
                                <SheetClose
                                    render={<Button type="button" variant="ghost" size="icon" aria-label={t("common.close")} />}
                                >
                                    <X aria-hidden />
                                </SheetClose>
                            </div>
                            <div className="min-h-0 flex-1">{history}</div>
                        </SheetContent>
                    </Sheet>
                    <p className="min-w-0 flex-1 truncate px-1 text-sm font-medium">{t("chat.title")}</p>
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className={historyShown ? "md:hidden" : undefined}
                        aria-label={t("chat.newChat")}
                        disabled={pending}
                        onClick={startNewChat}
                    >
                        <SquarePen aria-hidden />
                    </Button>
                </header>
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
