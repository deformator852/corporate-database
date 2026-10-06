export const ROLES_PER_PAGE = 20;

/** A role as other records show it. */
export type RoleRef = {
    key: string;
    name: string;
    protected?: boolean;
};

export type PermissionRef = {
    key: string;
    name: string;
};

export type RoleListItem = {
    key: string;
    name: string;
    description: string;
    protected: boolean;
    permissions: PermissionRef[];
};

export type RoleListPage = {
    items: RoleListItem[];
    page: number;
    per_page: number;
    total: number;
    pages: number;
};

export type RoleWritePayload = {
    name?: string;
    description: string;
    permission_keys: string[];
};
