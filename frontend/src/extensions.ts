// Loads project customizations from src/custom/<name>/index.ts(x).
// Upstream never ships files under src/custom/, so pulling updates does not
// conflict with them. See documentations/customization/.
import type {RouteObject} from "react-router";

import type {MessageOverrides} from "@/shared/i18n/messages";
import type {ThemeOption} from "@/theme/themes";
import type {NavItem} from "@/widgets/sidebar/model/nav";

export type Extension = {
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

const modules = import.meta.glob<Extension>("./custom/*/index.{ts,tsx}", {
    eager: true,
    import: "default",
});

export const extensions: Extension[] = Object.keys(modules)
    .sort()
    .map((path) => modules[path]);

export function mergeByKey<T>(core: T[], custom: T[], key: (item: T) => unknown): T[] {
    const replaced = new Set(custom.map(key));
    return [...core.filter((item) => !replaced.has(key(item))), ...custom];
}
