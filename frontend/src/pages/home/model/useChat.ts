import {useCallback, useEffect, useRef, useState} from "react";

import {connectChatSocket, type ChatSocket} from "@pages/home/api/chat";
import {getConversation, listConversations, rateAnswer} from "@pages/home/api/history";
import {
    ChatCancelledError,
    ChatRequestError,
    type ChatAskOptions,
    type ChatConversationItem,
    type ChatDocument,
    type ChatMessage,
    type ChatStatus,
} from "@pages/home/model/chat";
import {type AnswerRating} from "@/entities/chat/model";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {getApiErrorMessage} from "@/shared/lib/api/errors";

/** Chat limits (backend services/chat/limit.py): the question was refused
 * before it was saved or answered. */
const NOT_ACCEPTED = new Set(["busy", "rate_limited"]);

function nextId() {
    return crypto.randomUUID();
}

/** The chat on screen and the saved chats: asking over the socket, stopping,
 * retrying, opening and deleting saved chats. */
export function useChat() {
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
    // Documents the questions are limited to; empty means all.
    const [documents, setDocuments] = useState<ChatDocument[]>([]);
    // What the last question was sent with, so Try again sends it the same way.
    const lastOptions = useRef<ChatAskOptions>({});

    // Search in the saved chats; empty lists them all.
    const [historyQuery, setHistoryQuery] = useState("");
    // Only the newest list request may show: an older search can answer later.
    const historyRequest = useRef(0);

    const reloadHistory = useCallback(() => {
        const request = ++historyRequest.current;
        void listConversations(historyQuery)
            .then((items) => {
                if (request === historyRequest.current) {
                    setConversations(items);
                    setHistoryError(null);
                }
            })
            .catch((reason) => {
                if (request === historyRequest.current) {
                    setHistoryError(getApiErrorMessage(reason, t("chat.historyLoadError")));
                }
            });
    }, [t, historyQuery]);

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

    async function send(history: ChatMessage[], options: ChatAskOptions) {
        lastOptions.current = options;
        const socket = socketRef.current;
        if (socket == null) {
            setError(t("chat.errorSend"));
            setStatus("error");
            return;
        }
        setStatus("pending");
        setError(null);
        let partial = "";
        const appendAnswer = (content: string, sources: ChatMessage["sources"] = [], messageId?: number) =>
            setMessages((current) => [...current, {id: nextId(), role: "assistant", content, sources, messageId}]);
        try {
            const reply = await socket.send(
                history.map(({role, content}) => ({role, content})),
                conversationId,
                {
                    // Known before the answer, so a stopped first question
                    // still continues in its chat.
                    onStarted: setConversationId,
                    onDelta: (piece) => {
                        partial += piece;
                        setStreaming(partial);
                    },
                },
                options,
            );
            appendAnswer(reply.content, reply.sources, reply.messageId);
            setConversationId(reply.conversationId);
            reloadHistory();
            setStatus("idle");
        } catch (caught) {
            if (caught instanceof ChatCancelledError) {
                // Keep what was already written before Stop.
                if (partial.trim()) {
                    appendAnswer(partial.trim());
                }
                // The server saved the question and what was written.
                reloadHistory();
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
            if (caught instanceof ChatRequestError && caught.code === "not_found" && conversationId != null) {
                // The saved chat was cleared from the history: Try again
                // continues in a new chat, with what is on screen.
                setConversationId(null);
                lastOptions.current = {documentIds: options.documentIds};
                reloadHistory();
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
        void send(history, {documentIds: documents.map((document) => document.id)});
    }

    /** Asks the last question again; the new answer replaces the last one. */
    function regenerate() {
        const last = messages.at(-1);
        if (status === "pending" || last?.role !== "assistant" || last.messageId == null) {
            return;
        }
        const history = messages.slice(0, -1);
        setMessages(history);
        void send(history, {
            documentIds: documents.map((document) => document.id),
            replaceMessageId: last.messageId,
        });
    }

    function handleCancel() {
        socketRef.current?.cancel();
    }

    function startNewChat() {
        setMessages([]);
        setConversationId(null);
        setDocuments([]);
        setError(null);
        setStatus("idle");
    }

    async function openConversation(id: number) {
        try {
            const conversation = await getConversation(id);
            setMessages(
                conversation.messages.map((message) => ({
                    id: String(message.id),
                    role: message.role,
                    content: message.content,
                    sources: message.sources,
                    messageId: message.id,
                    rating: message.rating,
                })),
            );
            setConversationId(conversation.id);
            setDocuments([]);
            setError(null);
            setStatus("idle");
        } catch (reason) {
            setError(getApiErrorMessage(reason, t("chat.conversationLoadError")));
            setStatus("error");
        }
    }

    function handleRetry() {
        if (status === "pending") {
            return;
        }
        void send(messages, lastOptions.current);
    }

    /** Shown at once; put back if the server refuses it. */
    async function rate(message: ChatMessage, rating: AnswerRating | null) {
        if (conversationId == null || message.messageId == null) {
            return;
        }
        const setRating = (value: AnswerRating | null | undefined) =>
            setMessages((current) => current.map((item) => (item.id === message.id ? {...item, rating: value} : item)));
        setRating(rating);
        try {
            await rateAnswer(conversationId, message.messageId, rating);
        } catch (reason) {
            setRating(message.rating);
            setError(getApiErrorMessage(reason, t("chat.rating.error")));
        }
    }

    return {
        messages,
        draft,
        setDraft,
        status,
        error,
        streaming,
        conversationId,
        conversations,
        historyError,
        historyQuery,
        searchHistory: setHistoryQuery,
        documents,
        setDocuments,
        submit: handleSubmit,
        cancel: handleCancel,
        retry: handleRetry,
        regenerate,
        startNewChat,
        openConversation,
        rate,
    };
}
