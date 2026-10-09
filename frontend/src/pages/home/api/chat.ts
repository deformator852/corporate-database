import {
    ChatRequestError,
    ChatCancelledError,
    CHAT_HISTORY,
    isChatServerMessage,
    type ChatAskMessage,
    type ChatAskOptions,
    type ChatCancelMessage,
    type ChatMessage,
    type ChatReply,
    type ChatServerMessage,
} from "@pages/home/model/chat";
import {apiSocketUrl, openSocket} from "@/shared/lib/ws";

const FALLBACK = "Could not send the message.";

export type ChatHandlers = {
    /** The question is saved in this chat; comes before any answer. */
    onStarted?: (conversationId: number) => void;
    /** A piece of the answer as it is written. */
    onDelta?: (piece: string) => void;
};

export type ChatSocket = {
    /** Resolves with the full answer. */
    send: (
        messages: Pick<ChatMessage, "role" | "content">[],
        conversationId: number | null,
        handlers?: ChatHandlers,
        options?: ChatAskOptions,
    ) => Promise<ChatReply>;
    cancel: () => void;
    close: () => void;
};

type Pending = {
    resolve: (reply: ChatReply) => void;
    reject: (error: Error) => void;
    handlers: ChatHandlers;
};

/** One question at a time over a socket that reconnects; a drop fails the
 * question being answered. */
export function connectChatSocket(): ChatSocket {
    let closed = false;
    let pending: Pending | null = null;

    const failPending = (message: string, code = "unavailable") => {
        pending?.reject(new ChatRequestError(code, message));
        pending = null;
    };

    const finish = (message: Exclude<ChatServerMessage, {type: "delta" | "started"}>) => {
        const current = pending;
        pending = null;
        if (current == null) {
            return;
        }
        if (message.type === "error") {
            current.reject(new ChatRequestError(message.code, message.message));
        } else if (message.type === "cancelled") {
            current.reject(new ChatCancelledError());
        } else {
            current.resolve({
                content: message.content,
                conversationId: message.conversation_id,
                messageId: message.message_id,
                sources: message.sources,
            });
        }
    };

    const onMessage = (data: string) => {
        let parsed: unknown;
        try {
            parsed = JSON.parse(data);
        } catch {
            failPending(FALLBACK, "invalid");
            return;
        }
        if (!isChatServerMessage(parsed) || pending == null) {
            return;
        }
        if (parsed.type === "started") {
            pending.handlers.onStarted?.(parsed.conversation_id);
        } else if (parsed.type === "delta") {
            pending.handlers.onDelta?.(parsed.content);
        } else {
            finish(parsed);
        }
    };

    const live = openSocket(apiSocketUrl("/chat/ws"), {onMessage, onDrop: () => failPending(FALLBACK)});

    return {
        send(messages, conversationId, handlers = {}, options = {}) {
            const body: ChatAskMessage = {
                type: "ask",
                messages: messages.slice(-CHAT_HISTORY),
                conversation_id: conversationId,
                document_ids: options.documentIds ?? [],
                replace_message_id: options.replaceMessageId ?? null,
            };
            const target = live.current();
            if (target == null || closed) {
                return Promise.reject(new ChatRequestError("unavailable", FALLBACK));
            }
            if (pending != null) {
                return Promise.reject(new ChatRequestError("invalid", FALLBACK));
            }
            return new Promise<ChatReply>((resolve, reject) => {
                pending = {resolve, reject, handlers};
                void waitUntilOpen(target).then(
                    () => {
                        // Replaced or closed meanwhile: the question is lost.
                        if (live.current() !== target || target.readyState !== WebSocket.OPEN) {
                            failPending(FALLBACK);
                            return;
                        }
                        target.send(JSON.stringify(body));
                    },
                    () => failPending(FALLBACK),
                );
            });
        },
        cancel() {
            const target = live.current();
            if (target == null || pending == null || closed) {
                return;
            }
            if (target.readyState !== WebSocket.OPEN) {
                failPending(FALLBACK);
                return;
            }
            const body: ChatCancelMessage = {type: "cancel"};
            target.send(JSON.stringify(body));
        },
        close() {
            closed = true;
            failPending(FALLBACK);
            live.close();
        },
    };
}

function waitUntilOpen(socket: WebSocket): Promise<void> {
    if (socket.readyState === WebSocket.OPEN) {
        return Promise.resolve();
    }
    if (
        socket.readyState === WebSocket.CLOSING ||
        socket.readyState === WebSocket.CLOSED
    ) {
        return Promise.reject();
    }
    return new Promise((resolve, reject) => {
        socket.addEventListener("open", () => resolve(), {once: true});
        socket.addEventListener("error", () => reject(), {once: true});
        socket.addEventListener("close", () => reject(), {once: true});
    });
}
