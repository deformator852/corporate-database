export const PERMISSIONS_PER_PAGE = 20;

export type RoleRef = {
    key: string;
    name: string;
};

export type PermissionListItem = {
    key: string;
    name: string;
    description: string;
    roles: RoleRef[];
};

export type PermissionListPage = {
    items: PermissionListItem[];
    page: number;
    per_page: number;
    total: number;
    pages: number;
};
