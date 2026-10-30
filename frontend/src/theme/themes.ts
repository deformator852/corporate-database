import {extensions, mergeByKey} from "@/extensions";
import type {CustomMessageKey, MessageKey} from "@/shared/i18n/messages";

export type ThemeOption = {
    /** Value of `data-theme` on <html>; style it with `[data-theme="<id>"]`. */
    id: string;
    labelKey: MessageKey | CustomMessageKey;
    /** Adds the `.dark` class and a dark color scheme. */
    dark?: boolean;
};

// The theme of users who have not picked one, unless an extension sets
// `defaultTheme`. Keep `data-theme` in index.html in line with it.
const LEDGER: ThemeOption = {id: "ledger", labelKey: "theme.ledger"};

const CORE_THEMES: ThemeOption[] = [
    {id: "neutral", labelKey: "theme.neutral"},
    LEDGER,
    {id: "slate", labelKey: "theme.slate", dark: true},
    {id: "midnight", labelKey: "theme.midnight", dark: true},
    {id: "vault", labelKey: "theme.vault", dark: true},
];

export const THEMES = mergeByKey(
    CORE_THEMES,
    extensions.flatMap((extension) => extension.themes ?? []),
    (theme) => theme.id,
);

export const DEFAULT_THEME: ThemeOption =
    THEMES.find(
        (theme) => theme.id === extensions.findLast((e) => e.defaultTheme)?.defaultTheme,
    ) ?? LEDGER;

export const THEME_STORAGE_KEY = "ui-theme";

export function findTheme(id: string | null): ThemeOption | undefined {
    return THEMES.find((theme) => theme.id === id);
}
