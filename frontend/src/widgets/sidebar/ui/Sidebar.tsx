import {useMemo} from "react";
import {NavLink} from "react-router";

import {useI18n} from "@/shared/i18n/I18nProvider";
import type {MessageKey} from "@/shared/i18n/messages";
import {can} from "@/shared/lib/api/me.ts";

type NavItem = {
    to: string;
    labelKey: MessageKey;
    end?: boolean;
    can?: string;
};

export function Sidebar() {
    const {t} = useI18n();
    const nav = useMemo(
        () =>
            [
                {to: "/", labelKey: "nav.home", end: true},
                {
                    to: "/documents",
                    labelKey: "nav.documents",
                    end: true,
                    can: "documents.list",
                },
                {to: "/users", labelKey: "nav.users", end: true, can: "users.list"},
                {to: "/roles", labelKey: "nav.roles", end: true, can: "roles.list"},
                {
                    to: "/permissions",
                    labelKey: "nav.permissions",
                    end: true,
                    can: "permissions.list",
                },
            ] satisfies NavItem[],
        [],
    );

    return (
        <aside className="app-layout__sidebar" aria-label={t("nav.label")}>
            <nav className="app-layout__nav">
                {nav.map((item) =>
                    (!item.can || can(item.can)) ? (
                        <NavLink
                            key={item.to}
                            to={item.to}
                            end={item.end}
                            className={({isActive}) =>
                                `app-layout__nav-link${isActive ? " app-layout__nav-link--active" : ""}`
                            }
                        >
                            {t(item.labelKey)}
                        </NavLink>
                    ) : null,
                )}
            </nav>
        </aside>
    );
}
