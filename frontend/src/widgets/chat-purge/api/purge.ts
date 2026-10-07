import {api} from "@/shared/lib/api/client";
import type {PurgeRange} from "@/widgets/chat-purge/model/purge";

/** Deletes the chats last active in `range`, of one user or of everyone the
 * actor may reach; resolves with how many were deleted. */
export async function purgeChats(range: PurgeRange, userId?: number): Promise<number> {
    const {data} = await api.post<{deleted: number}>("/chat/review/purge", {...range, user_id: userId ?? null});
    return data.deleted;
}
