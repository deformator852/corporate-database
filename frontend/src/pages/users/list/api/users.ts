import {api} from "@/shared/lib/api/client";
import type {RoleRef, UserListItem, UserWritePayload} from "@pages/users/list/model/users";

export async function getRoles(): Promise<RoleRef[]> {
    const {data} = await api.get<RoleRef[]>("/users/roles");
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
