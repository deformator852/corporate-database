export type SessionUser = {
    id: number;
    first_name: string;
    last_name: string;
    email: string;
    permissions: string[];
    /** Chosen in the header; null: the default language. */
    language: string | null;
};
