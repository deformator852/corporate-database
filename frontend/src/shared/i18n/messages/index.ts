import {en, type MessageKey} from "./en";
import {es} from "./es";
import {fr} from "./fr";

export type {MessageKey};
/** Keys added by src/custom extensions. */
export type CustomMessageKey = `custom.${string}`;
export {en};

const LOCALES = ["en", "es", "fr"] as const;
export type Locale = (typeof LOCALES)[number];

/** Fallback for keys a locale lacks. */
export const DEFAULT_LOCALE: Locale = "en";

// APP_LANGUAGE (the default) and APP_LANGUAGES (the ones users switch
// between) from backend/.env, injected by vite.config.ts; set by `uv run install`.
const SYSTEM_LOCALE: Locale = isLocale(import.meta.env.APP_LANGUAGE)
    ? import.meta.env.APP_LANGUAGE
    : DEFAULT_LOCALE;

/** The default language first. */
export const ENABLED_LOCALES: readonly Locale[] = [
    ...new Set([SYSTEM_LOCALE, ...(import.meta.env.APP_LANGUAGES ?? "").split(",").map((code) => code.trim()).filter(isLocale)]),
];

/** Each language's name in itself, for the switcher. */
export const LOCALE_NAMES: Record<Locale, string> = {
    en: "English",
    es: "Español",
    fr: "Français",
};

export const messages: Record<Locale, Record<MessageKey, string>> = {
    en,
    es,
    fr,
};

export type MessageOverrides = Partial<
    Record<Locale, Partial<Record<MessageKey | CustomMessageKey, string>>>
>;

export function isLocale(value: string | null | undefined): value is Locale {
    return LOCALES.includes(value as Locale);
}

const HTML_LANG: Record<Locale, string> = {
    en: "en",
    es: "es",
    fr: "fr",
};

export function localeHtmlLang(locale: Locale): string {
    return HTML_LANG[locale];
}

export function localeIntlTag(locale: Locale): string {
    return locale;
}
