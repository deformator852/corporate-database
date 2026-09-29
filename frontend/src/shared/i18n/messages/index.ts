import {en, type MessageKey} from "./en";
import {es} from "./es";
import {fr} from "./fr";

export type {MessageKey};
/** Keys added by src/custom extensions. */
export type CustomMessageKey = `custom.${string}`;
export {en};

export const LOCALES = ["en", "es", "fr"] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "en";

// APP_LANGUAGE from backend/.env, injected by vite.config.ts; set by `uv run setup`.
export const LOCALE: Locale = isLocale(import.meta.env.APP_LANGUAGE)
    ? import.meta.env.APP_LANGUAGE
    : DEFAULT_LOCALE;

export const messages: Record<Locale, Record<MessageKey, string>> = {
    en,
    es,
    fr,
};

export type MessageOverrides = Partial<
    Record<Locale, Partial<Record<MessageKey | CustomMessageKey, string>>>
>;

export function isLocale(value: string | undefined): value is Locale {
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
