import {
    ChatRequestError,
    ChatCancelledError,
    CHAT_HISTORY,
    isChatServerMessage,
    type ChatAskMessage,
    type ChatCancelMessage,
    type ChatMessage,
    type ChatReply,
    type ChatServerMessage,
} from "@pages/home/model/chat";
import {reconnectDelay} from "@/shared/lib/ws";

const FALLBACK = "Could not send the message.";

export function chatSocketUrl(): string {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/api/v1/chat/ws`;
}

export type ChatSocket = {
    /** Resolves with the full answer; `onDelta` receives pieces as they arrive. */
    send: (
        messages: Pick<ChatMessage, "role" | "content">[],
        conversationId: number | null,
        onDelta?: (piece: string) => void,
    ) => Promise<ChatReply>;
    cancel: () => void;
    close: () => void;
};

export function connectChatSocket(): ChatSocket {
    let closed = false;
    let socket: WebSocket | null = null;
    let timer: number | undefined;
    let pending: {
        resolve: (reply: ChatReply) => void;
        reject: (error: Error) => void;
        onDelta?: (piece: string) => void;
    } | null = null;

    const failPending = (message: string, code = "unavailable") => {
        if (pending == null) {
            return;
        }
        pending.reject(new ChatRequestError(code, message));
        pending = null;
    };

    const open = () => {
        if (closed) {
            return;
        }
        const next = new WebSocket(chatSocketUrl());
        socket = next;
        next.addEventListener("message", (event) => {
            if (typeof event.data !== "string") {
                return;
            }
            let parsed: unknown;
            try {
                parsed = JSON.parse(event.data);
            } catch {
                failPending(FALLBACK, "invalid");
                return;
            }
            if (!isChatServerMessage(parsed) || pending == null) {
                return;
            }
            if (parsed.type === "delta") {
                pending.onDelta?.(parsed.content);
                return;
            }
            finish(parsed);
        });
        next.addEventListener("close", (event) => {
            failPending(FALLBACK);
            if (closed || socket !== next) {
                return;
            }
            void reconnectDelay(event.code).then((delay) => {
                if (delay !== null && !closed) {
                    timer = window.setTimeout(open, delay);
                }
            });
        });
        next.addEventListener("error", () => {
            next.close();
        });
    };

    const finish = (message: Exclude<ChatServerMessage, {type: "delta"}>) => {
        if (pending == null) {
            return;
        }
        const current = pending;
        pending = null;
        if (message.type === "error") {
            current.reject(new ChatRequestError(message.code, message.message));
            return;
        }
        if (message.type === "cancelled") {
            current.reject(new ChatCancelledError());
            return;
        }
        current.resolve({
            content: message.content,
            conversationId: message.conversation_id,
            sources: message.sources,
        });
    };

    // Deferred so an immediate close() (React StrictMode remount) cancels it
    // instead of aborting a socket mid-handshake.
    timer = window.setTimeout(open, 0);

    return {
        send(messages, conversationId, onDelta) {
            const body: ChatAskMessage = {
                type: "ask",
                messages: messages.slice(-CHAT_HISTORY),
                conversation_id: conversationId,
            };
            const target = socket;
            if (target == null || closed) {
                return Promise.reject(new ChatRequestError("unavailable", FALLBACK));
            }
            if (pending != null) {
                return Promise.reject(new ChatRequestError("invalid", FALLBACK));
            }
            return new Promise<ChatReply>((resolve, reject) => {
                pending = {resolve, reject, onDelta};
                void waitUntilOpen(target).then(
                    () => {
                        if (socket !== target || target.readyState !== WebSocket.OPEN) {
                            failPending(FALLBACK);
                            return;
                        }
                        target.send(JSON.stringify(body));
                    },
                    () => {
                        failPending(FALLBACK);
                    },
                );
            });
        },
        cancel() {
            const target = socket;
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
            if (timer !== undefined) {
                window.clearTimeout(timer);
            }
            socket?.close();
            socket = null;
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
