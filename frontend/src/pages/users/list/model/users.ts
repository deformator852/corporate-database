export const USERS_PER_PAGE = 20;

export type RoleRef = {
    key: string;
    name: string;
    protected?: boolean;
};

export type UserListItem = {
    id: number;
    first_name: string;
    last_name: string;
    email: string;
    roles: RoleRef[];
    is_last_admin: boolean;
    /** Cannot sign in; the account and its history stay. */
    disabled: boolean;
};

export type UserListPage = {
    items: UserListItem[];
    page: number;
    per_page: number;
    total: number;
    pages: number;
};

export type UserWritePayload = {
    first_name: string;
    last_name: string;
    email: string;
    password?: string;
    role_keys: string[];
};
