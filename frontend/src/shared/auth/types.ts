export type SessionUser = {
    id: number;
    first_name: string;
    last_name: string;
    email: string;
    permissions: string[];
    /** Chosen in the header; null: the default language. */
    language: string | null;
    /** Signs in with an Archfold password, which they may change. False for
     * SSO users, and for everyone while single sign-on is on. */
    uses_password: boolean;
    /** The AI model is a Llama model: its license asks for "Built with Llama". */
    built_with_llama?: boolean;
};
