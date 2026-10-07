import type {AnswerRating, ChatSource} from "@/entities/chat/model";

type ChatRole = "user" | "assistant";

/** A document the user chose to ask about. */
export type ChatDocument = {id: number; name: string};

/** Most documents a question may be limited to (backend ChatAskSchema). */
export const MAX_CHAT_DOCUMENTS = 20;

export type ChatMessage = {
    id: string;
    role: ChatRole;
    content: string;
    sources?: ChatSource[];
    /** Saved on the server under this id (answers can then be rated). */
    messageId?: number;
    rating?: AnswerRating | null;
};

/** A finished answer: the text, the saved chat it belongs to, its sources. */
export type ChatReply = {
    content: string;
    conversationId: number;
    /** The saved answer; ratings refer to it. */
    messageId: number;
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
        rating: AnswerRating | null;
    }[];
};

/** "refused": the server did not accept the question (chat limits); it is
 * back in the input, so there is nothing to retry. */
export type ChatStatus = "idle" | "pending" | "error" | "refused";

/** Most messages the server accepts (ChatRequestSchema); it keeps the newest
 * that fit a quarter of the model context. */
export const CHAT_HISTORY = 40;

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
    /** Answer only from these documents; empty searches all. */
    document_ids: number[];
    /** Regenerate: the new answer replaces this one, the chat's last. */
    replace_message_id: number | null;
};

/** What a question is asked with besides the messages. */
export type ChatAskOptions = {
    documentIds?: number[];
    replaceMessageId?: number | null;
};

export type ChatCancelMessage = {
    type: "cancel";
};

export type ChatServerMessage =
    | {type: "started"; conversation_id: number}
    | {type: "delta"; content: string}
    | {type: "answer"; content: string; conversation_id: number; message_id: number; sources: ChatSource[]}
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
    if (payload.type === "started") {
        return typeof (payload as {conversation_id?: unknown}).conversation_id === "number";
    }
    if (payload.type === "delta") {
        return typeof payload.content === "string";
    }
    if (payload.type === "answer") {
        const answer = payload as {conversation_id?: unknown; message_id?: unknown; sources?: unknown};
        return (
            typeof payload.content === "string" &&
            typeof answer.conversation_id === "number" &&
            typeof answer.message_id === "number" &&
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
