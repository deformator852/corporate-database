import {api} from "@/shared/lib/api/client";
import {
    USERS_PER_PAGE,
    type UserListPage,
} from "@pages/users/list/model/users";

export async function getUsers(
    page: number,
    perPage = USERS_PER_PAGE,
): Promise<UserListPage> {
    const {data} = await api.get<UserListPage>("/users", {
        params: {page, per_page: perPage},
    });
    return data;
}
