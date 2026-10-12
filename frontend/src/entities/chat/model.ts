/** A document an answer was built from. */
export type ChatSource = {
    id: number;
    name: string;
    filename: string;
    /** The passage the answer was taken from; absent on older answers. */
    chunk?: number | null;
};

export type AnswerRating = "up" | "down";

/** Router state of a link to one user's chat history: their name, shown
 * even when they have no chats to take it from. */
export type ChatHistoryLinkState = {userName: string};

/** The address fragment of a message on the chat review page, which
 * scrolls to it and marks it (#message-12). */
export function chatMessageAnchor(messageId: number): string {
    return `message-${messageId}`;
}
