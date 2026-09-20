import {api} from "@/shared/lib/api/client";
import {
    USERS_PER_PAGE,
    type UserListItem,
    type UserListPage,
    type UserWritePayload,
} from "@pages/users/list/model/users";

export async function getUsersPage(
    page: number,
    perPage = USERS_PER_PAGE,
): Promise<UserListPage> {
    const {data} = await api.get<UserListPage>("/users", {
        params: {page, per_page: perPage},
    });
    return data;
}

export async function createUser(payload: UserWritePayload): Promise<UserListItem> {
    const {data} = await api.post<UserListItem>("/users", payload);
    return data;
}

export async function updateUser(
    userId: number,
    payload: UserWritePayload,
): Promise<UserListItem> {
    const {data} = await api.patch<UserListItem>(`/users/${userId}`, payload);
    return data;
}

export async function deleteUser(userId: number): Promise<void> {
    await api.delete(`/users/${userId}`);
}
