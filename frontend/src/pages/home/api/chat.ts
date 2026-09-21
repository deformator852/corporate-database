import type {ChatMessage} from "@pages/home/model/chat";

function delay(ms: number) {
    return new Promise((resolve) => {
        window.setTimeout(resolve, ms);
    });
}

export async function sendChatMessage(
    messages: Pick<ChatMessage, "role" | "content">[],
): Promise<string> {
    const last = messages.at(-1)?.content.trim() ?? "";
    await delay(650);
    return `I received: "${last}". The model is not connected yet.`;
}
