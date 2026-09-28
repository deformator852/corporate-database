import {api} from "@/shared/lib/api/client";
import type {AuditCursorPage} from "@pages/audit/model/audit";
import {USER_ACTIVITY_PAGE, type UserDetail} from "@pages/users/detail/model/user";

export async function getUser(userId: number): Promise<UserDetail> {
    const {data} = await api.get<UserDetail>(`/users/${userId}`);
    return data;
}

/** Newest first; pass `next_cursor` of the previous page as `before`. */
export async function getUserActivity(
    userId: number,
    before: number | null,
    limit = USER_ACTIVITY_PAGE,
): Promise<AuditCursorPage> {
    const {data} = await api.get<AuditCursorPage>(`/users/${userId}/activity`, {
        params: {before: before ?? undefined, limit},
    });
    return data;
}
