export type ChatRole = "user" | "assistant";

export type ChatMessage = {
    id: string;
    role: ChatRole;
    content: string;
};

export type ChatStatus = "idle" | "pending" | "error";

export const CHAT_HISTORY = 6;

export class ChatRequestError extends Error {
    readonly code: string;

    constructor(code: string, message: string) {
        super(message);
        this.name = "ChatRequestError";
        this.code = code;
    }
}

export type ChatAskMessage = {
    type: "ask";
    messages: Pick<ChatMessage, "role" | "content">[];
};

export type ChatCancelMessage = {
    type: "cancel";
};

export type ChatServerMessage =
    | {type: "answer"; content: string}
    | {type: "cancelled"}
    | {type: "error"; code: string; message: string};

export class ChatCancelledError extends Error {
    constructor() {
        super("Generation stopped.");
        this.name = "ChatCancelledError";
    }
}

export function isChatServerMessage(value: unknown): value is ChatServerMessage {
    if (value == null || typeof value !== "object") {
        return false;
    }
    const payload = value as {
        type?: unknown;
        content?: unknown;
        code?: unknown;
        message?: unknown;
    };
    if (payload.type === "answer") {
        return typeof payload.content === "string";
    }
    if (payload.type === "cancelled") {
        return true;
    }
    if (payload.type === "error") {
        return typeof payload.code === "string" && typeof payload.message === "string";
    }
    return false;
}
