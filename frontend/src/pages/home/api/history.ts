import {api} from "@/shared/lib/api/client";
import type {ChatConversation, ChatConversationItem} from "@pages/home/model/chat";

type ConversationPage = {
    items: ChatConversationItem[];
    total: number;
};

export async function listConversations(): Promise<ChatConversationItem[]> {
    const {data} = await api.get<ConversationPage>("/chat/conversations", {
        params: {per_page: 50},
    });
    return data.items;
}

export async function getConversation(id: number): Promise<ChatConversation> {
    const {data} = await api.get<ChatConversation>(`/chat/conversations/${id}`);
    return data;
}

export async function deleteConversation(id: number): Promise<void> {
    await api.delete(`/chat/conversations/${id}`);
}
