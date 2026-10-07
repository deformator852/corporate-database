import type {AnswerRating, ChatSource} from "@/entities/chat/model";

export const CHAT_HISTORY_PER_PAGE = 20;

type ChatOwner = {id: number; name: string; email: string};

type ReviewedChat = {
    id: number;
    title: string;
    created_at: string;
    updated_at: string;
    message_count: number;
    user: ChatOwner;
};

export type ReviewedChatPage = {
    items: ReviewedChat[];
    page: number;
    per_page: number;
    total: number;
    pages: number;
};

export type ReviewedConversation = {
    id: number;
    title: string;
    user: ChatOwner;
    messages: {
        id: number;
        role: "user" | "assistant";
        content: string;
        sources: ChatSource[];
        created_at: string;
        rating: AnswerRating | null;
    }[];
};
