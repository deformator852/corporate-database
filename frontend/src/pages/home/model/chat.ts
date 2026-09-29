export type ChatRole = "user" | "assistant";

/** A document an answer was built from. */
export type ChatSource = {
    id: number;
    name: string;
    filename: string;
};

export type ChatMessage = {
    id: string;
    role: ChatRole;
    content: string;
    sources?: ChatSource[];
};

/** A finished answer: the text, the saved chat it belongs to, its sources. */
export type ChatReply = {
    content: string;
    conversationId: number;
    sources: ChatSource[];
};

export type ChatConversationItem = {
    id: number;
    title: string;
    updated_at: string;
};

export type ChatConversation = {
    id: number;
    title: string;
    messages: {
        id: number;
        role: ChatRole;
        content: string;
        sources: ChatSource[];
        created_at: string;
    }[];
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
    /** Continue a saved chat; null starts a new one. */
    conversation_id: number | null;
};

export type ChatCancelMessage = {
    type: "cancel";
};

export type ChatServerMessage =
    | {type: "delta"; content: string}
    | {type: "answer"; content: string; conversation_id: number; sources: ChatSource[]}
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
    if (payload.type === "delta") {
        return typeof payload.content === "string";
    }
    if (payload.type === "answer") {
        const answer = payload as {conversation_id?: unknown; sources?: unknown};
        return (
            typeof payload.content === "string" &&
            typeof answer.conversation_id === "number" &&
            Array.isArray(answer.sources)
        );
    }
    if (payload.type === "cancelled") {
        return true;
    }
    if (payload.type === "error") {
        return typeof payload.code === "string" && typeof payload.message === "string";
    }
    return false;
}
