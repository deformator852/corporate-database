import {api} from "@/shared/lib/api/client";
import {
    ROLE_PERMISSION_PAGE_SIZE,
    ROLES_PER_PAGE,
    type PermissionOptionPage,
    type RoleListItem,
    type RoleListPage,
    type RoleWritePayload,
} from "@pages/roles/list/model/roles";

export async function getRolesPage(
    page: number,
    perPage = ROLES_PER_PAGE,
): Promise<RoleListPage> {
    const {data} = await api.get<RoleListPage>("/roles", {
        params: {page, per_page: perPage},
    });
    return data;
}

export async function getPermissionOptions(
    page: number,
    q = "",
    perPage = ROLE_PERMISSION_PAGE_SIZE,
): Promise<PermissionOptionPage> {
    const {data} = await api.get<PermissionOptionPage>("/roles/permissions", {
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
