import {api} from "@/shared/lib/api/client";
import type {ChatConversation, ChatConversationItem} from "@pages/home/model/chat";
import type {AnswerRating} from "@/entities/chat/model";

type ConversationPage = {
    items: ChatConversationItem[];
    total: number;
};

/** The newest saved chats; `query` keeps those whose title or messages hold it. */
export async function listConversations(query = ""): Promise<ChatConversationItem[]> {
    const {data} = await api.get<ConversationPage>("/chat/conversations", {
        params: {per_page: 50, q: query || undefined},
    });
    return data.items;
}

export async function getConversation(id: number): Promise<ChatConversation> {
    const {data} = await api.get<ChatConversation>(`/chat/conversations/${id}`);
    return data;
}

/** null takes the rating back. */
export async function rateAnswer(conversationId: number, messageId: number, rating: AnswerRating | null): Promise<void> {
    await api.put(`/chat/conversations/${conversationId}/messages/${messageId}/rating`, {rating});
}
