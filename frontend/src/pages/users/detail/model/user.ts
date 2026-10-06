export const USER_ACTIVITY_PAGE = 30;

export type UserDetail = {
    id: number;
    first_name: string;
    last_name: string;
    email: string;
    roles: {key: string; name: string}[];
    disabled: boolean;
    created_at: string;
    last_sign_in_at: string | null;
    actions_total: number;
};
