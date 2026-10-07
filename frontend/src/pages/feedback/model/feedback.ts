import type {AnswerRating, ChatSource} from "@/entities/chat/model";

export const FEEDBACK_PER_PAGE = 20;

/** An answer a user rated, with the question it replied to. */
export type RatedAnswer = {
    message_id: number;
    rating: AnswerRating;
    question: string;
    answer: string;
    sources: ChatSource[];
    rated_at: string;
    /** null once the user is deleted. */
    user: {id: number; name: string; email: string} | null;
};

export type RatedAnswerPage = {
    items: RatedAnswer[];
    page: number;
    per_page: number;
    total: number;
    pages: number;
};
