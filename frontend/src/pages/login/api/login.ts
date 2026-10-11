import {api} from "@/shared/lib/api/client";
import {API_PREFIX} from "@/shared/lib/api/config";
import type {SessionUser} from "@/shared/auth/types";
import type {LoginFormData} from "@pages/login/schema/loginForm";

/** What the sign-in page offers (backend /auth/methods). */
export type SignInMethods = {
    /** Corpus passwords sign in; false while single sign-on is on. */
    password: boolean;
    sso: {name: string} | null;
};

export async function getSignInMethods(): Promise<SignInMethods> {
    const {data} = await api.get<SignInMethods>("/auth/methods");
    return data;
}

/** A full-page navigation, not a request: the browser goes to the
 * company's sign-in page and comes back signed in. */
export const SSO_START_URL = `${API_PREFIX}/auth/sso/start`;

export async function login(payload: LoginFormData): Promise<SessionUser> {
    const {data} = await api.post<SessionUser>("/auth/login", payload);
    return data;
}
