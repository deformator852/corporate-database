import {api} from "@/shared/lib/api/client";
import {
    PERMISSIONS_PER_PAGE,
    type PermissionListPage,
} from "@pages/permissions/list/model/permissions";

export async function getPermissionsPage(
    page: number,
    perPage = PERMISSIONS_PER_PAGE,
    q = "",
): Promise<PermissionListPage> {
    const {data} = await api.get<PermissionListPage>("/permissions", {
        params: {page, per_page: perPage, q: q || undefined},
    });
    return data;
}
