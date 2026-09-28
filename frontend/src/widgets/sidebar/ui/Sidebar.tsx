import {NavLink} from "react-router";

import {extensions, mergeByKey} from "@/extensions";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {can} from "@/shared/lib/api/me.ts";
import {CORE_NAV} from "@/widgets/sidebar/model/nav";

const nav = mergeByKey(
    CORE_NAV,
    extensions.flatMap((extension) => extension.nav ?? []),
    (item) => item.to,
);

export function Sidebar() {
    const {t} = useI18n();

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
