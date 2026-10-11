import {render} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {createMemoryRouter, RouterProvider} from "react-router";

import {routes} from "@/router";
import type {SessionUser} from "@/shared/auth/types";
import {I18nProvider} from "@/shared/i18n/I18nProvider";
import type {Locale} from "@/shared/i18n/messages";
import {ThemeProvider} from "@/theme/ThemeProvider";
import {mockApi, reply, type MockApi} from "./api";

export function sessionUser(permissions: string[] = [], extra: Partial<SessionUser> = {}): SessionUser {
    return {
        id: 1,
        first_name: "Marta",
        last_name: "Ruiz",
        email: "marta@acme.io",
        permissions,
        language: null,
        uses_password: true,
        ...extra,
    } as SessionUser;
}

/**
 * The whole app at `path`, signed in as `user` (or signed out with null),
 * against a scripted API. Pages call `server.on(...)` for their own data.
 */
export function renderApp(
    path: string,
    user: SessionUser | null,
    script: (server: MockApi) => void = () => {},
    // Whatever backend/.env enables, tests run in English unless they ask.
    {locales = ["en"]}: {locales?: Locale[]} = {},
) {
    const server = mockApi();
    const signedOut = reply(401, {code: "unauthorized", message: "Not authenticated"});
    server.on("GET", "/auth/me", user ?? signedOut);
    server.on("GET", "/auth/methods", {password: true, sso: null});
    server.on("POST", "/auth/refresh", user ? {} : signedOut);
    server.on("GET", "/notifications", {items: [], page: 1, per_page: 20, total: 0, pages: 0, unread_count: 0});
    server.on("GET", "/chat/conversations", {items: [], page: 1, per_page: 30, total: 0, pages: 0});
    script(server);
    const router = createMemoryRouter(routes, {initialEntries: [path]});
    const view = render(
        <I18nProvider locales={locales}>
            <ThemeProvider>
                <RouterProvider router={router}/>
            </ThemeProvider>
        </I18nProvider>,
    );
    return {...view, router, server, user: userEvent.setup()};
}
