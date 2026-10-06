// Loads extensions: the paid features from src/advanced/<name>/index.ts(x),
// then customizations from src/custom/<name>/index.ts(x), so a customer can
// replace an advanced page, link, string or theme too.
// Upstream never ships files under src/custom/, so pulling updates does not
// conflict with them (see documentations/customization/). src/advanced/ is
// not in the core repository: the advanced edition puts its modules there.
// Core code never imports from either folder.
import type {RouteObject} from "react-router";

import type {MessageOverrides} from "@/shared/i18n/messages";
import type {ThemeOption} from "@/theme/themes";
import type {NavItem} from "@/widgets/sidebar/model/nav";

/** Raised when the extension points change incompatibly. */
export const CORE_API = 1;

export type Extension = {
    /** The extension API version it was written for; another one is skipped. */
    coreApi?: number;
    /** Pages inside the logged-in layout. A route with the same path (or `index`) replaces the core page. */
    routes?: RouteObject[];
    /** Sidebar links, after the core ones. The same `to` replaces a core link. */
    nav?: NavItem[];
    /** Per-locale strings. New keys start with `custom.`; core keys may be overridden. */
    messages?: MessageOverrides;
    /** Themes in the theme picker. Style them in a CSS file imported by this module. The same `id` replaces a core theme. */
    themes?: ThemeOption[];
    /** Theme id for users who have not picked one yet. The last extension that sets it wins. */
    defaultTheme?: string;
};

const advanced = import.meta.glob<Extension>("./advanced/*/index.{ts,tsx}", {eager: true, import: "default"});
const custom = import.meta.glob<Extension>("./custom/*/index.{ts,tsx}", {eager: true, import: "default"});

function loaded(modules: Record<string, Extension>): Extension[] {
    return Object.keys(modules)
        .sort()
        .filter((path) => {
            const wanted = modules[path].coreApi ?? CORE_API;
            if (wanted !== CORE_API) {
                console.error(`Extension ${path} needs extension API ${wanted}, this app has ${CORE_API}; skipped`);
            }
            return wanted === CORE_API;
        })
        .map((path) => modules[path]);
}

export const extensions: Extension[] = [...loaded(advanced), ...loaded(custom)];

/** Core items with extension items appended; an extension item replaces the
 * core one with the same key, and a later extension replaces an earlier one. */
export function mergeByKey<T>(core: T[], extra: T[], key: (item: T) => unknown): T[] {
    const latest = new Map(extra.map((item) => [key(item), item]));
    return [...core.filter((item) => !latest.has(key(item))), ...latest.values()];
}
