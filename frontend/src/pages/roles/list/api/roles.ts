import {api} from "@/shared/lib/api/client";
import {
    ROLES_PER_PAGE,
    type RoleListItem,
    type RoleListPage,
    type RoleWritePayload,
} from "@pages/roles/list/model/roles";

export async function getRolesPage(
    page: number,
    perPage = ROLES_PER_PAGE,
    q = "",
): Promise<RoleListPage> {
    const {data} = await api.get<RoleListPage>("/roles", {
        params: {page, per_page: perPage, q: q || undefined},
    });
    return data;
}

export async function createRole(payload: RoleWritePayload): Promise<RoleListItem> {
    const {data} = await api.post<RoleListItem>("/roles", payload);
    return data;
}

export async function updateRole(
    key: string,
    payload: RoleWritePayload,
): Promise<RoleListItem> {
    const {data} = await api.patch<RoleListItem>(`/roles/${key}`, payload);
    return data;
}

export async function deleteRole(key: string): Promise<void> {
    await api.delete(`/roles/${key}`);
}
