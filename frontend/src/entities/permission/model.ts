export const PERMISSIONS_PER_PAGE = 20;

type PermissionListItem = {
    key: string;
    name: string;
    description: string;
    roles: {key: string; name: string}[];
};

export type PermissionListPage = {
    items: PermissionListItem[];
    page: number;
    per_page: number;
    total: number;
    pages: number;
};
