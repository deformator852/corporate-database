import {en, type MessageKey} from "./en";
import {es} from "./es";
import {fr} from "./fr";
import {tr} from "./tr";
import {uk} from "./uk";

export type {MessageKey};
export {en};

export const LOCALES = ["en", "es", "uk", "tr", "fr"] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "en";
export const LOCALE_STORAGE_KEY = "ui-locale";

export const messages: Record<Locale, Record<MessageKey, string>> = {
    en,
    es,
    uk,
    tr,
    fr,
};

export function isLocale(value: string | null): value is Locale {
    return LOCALES.includes(value as Locale);
}

const HTML_LANG: Record<Locale, string> = {
    en: "en",
    es: "es",
    uk: "uk",
    tr: "tr",
    fr: "fr",
};

export function localeHtmlLang(locale: Locale): string {
    return HTML_LANG[locale];
}

export function localeIntlTag(locale: Locale): string {
    if (locale === "uk") {
        return "uk-UA";
    }
    return locale;
}
