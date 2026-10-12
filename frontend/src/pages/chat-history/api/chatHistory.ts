import {api} from "@/shared/lib/api/client";
import {
    CHAT_HISTORY_PER_PAGE,
    type ReviewedChatPage,
    type ReviewedConversation,
} from "@pages/chat-history/model/chatHistory";

/** Users' saved chats, newest activity first; `userId` limits them to one user. */
export async function getReviewedChats(page: number, userId: number | null): Promise<ReviewedChatPage> {
    const {data} = await api.get<ReviewedChatPage>("/chat/review/conversations", {
        params: {page, per_page: CHAT_HISTORY_PER_PAGE, user_id: userId ?? undefined},
    });
    return data;
}

/** One chat with its messages; reading it is recorded in the audit log. */
export async function getReviewedConversation(id: number): Promise<ReviewedConversation> {
    const {data} = await api.get<ReviewedConversation>(`/chat/review/conversations/${id}`);
    return data;
}

/** Deletes one chat with its messages and ratings; recorded in the audit log. */
export async function deleteReviewedChat(id: number): Promise<void> {
    await api.delete(`/chat/review/conversations/${id}`);
}
