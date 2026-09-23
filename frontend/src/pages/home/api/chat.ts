import {api} from "@/shared/lib/api/client";
import type {ChatMessage} from "@pages/home/model/chat";

export async function sendChatMessage(
    messages: Pick<ChatMessage, "role" | "content">[],
): Promise<string> {
    const {data} = await api.post<{content: string}>(
        "/chat",
        {messages},
        {timeout: 180_000},
    );
    return data.content;
}
