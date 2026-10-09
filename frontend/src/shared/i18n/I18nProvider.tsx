import {createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode} from "react";

import {api} from "@/shared/lib/api/client";

import {
    DEFAULT_LOCALE,
    ENABLED_LOCALES,
    localeHtmlLang,
    messages,
    isLocale,
    type CustomMessageKey,
    type Locale,
    type MessageKey,
    type MessageOverrides,
} from "./messages";

export type TranslateFn = (
    key: MessageKey | CustomMessageKey,
    params?: Record<string, string | number>,
) => string;

type I18nContextValue = {
    locale: Locale;
    /** The languages users switch between, the default first. */
    locales: readonly Locale[];
    setLocale: (locale: Locale) => void;
    t: TranslateFn;
};

const LOCALE_STORAGE_KEY = "corpus-locale";

const I18nContext = createContext<I18nContextValue | null>(null);

function interpolate(template: string, params?: Record<string, string | number>): string {
    if (!params) {
        return template;
    }
    return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) => {
        const value = params[name];
        return value === undefined ? `{{${name}}}` : String(value);
    });
}

function readStoredLocale(locales: readonly Locale[]): Locale {
    try {
        const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
        if (isLocale(stored) && locales.includes(stored)) {
            return stored;
        }
    } catch {
        // Storage blocked: the default language.
    }
    return locales[0] ?? DEFAULT_LOCALE;
}

/** The server translates its messages to the language the client names. */
function tellServer(locale: Locale) {
    api.defaults.headers.common["Accept-Language"] = locale;
}

export function I18nProvider({
    children,
    overrides = [],
    locales = ENABLED_LOCALES,
}: {
    children: ReactNode;
    overrides?: MessageOverrides[];
    locales?: readonly Locale[];
}) {
    const [locale, setLocaleState] = useState<Locale>(() => {
        const initial = readStoredLocale(locales);
        tellServer(initial);
        return initial;
    });

    const setLocale = useCallback(
        (next: Locale) => {
            if (!locales.includes(next)) {
                return;
            }
            tellServer(next);
            setLocaleState(next);
            try {
                localStorage.setItem(LOCALE_STORAGE_KEY, next);
            } catch {
                // Ignore persistence failures.
            }
        },
        [locales],
    );

    useEffect(() => {
        document.documentElement.lang = localeHtmlLang(locale);
    }, [locale]);

    const value = useMemo(() => {
        const merge = (code: Locale): Record<string, string> =>
            Object.assign({}, messages[code], ...overrides.map((o) => o[code]));
        const table = merge(locale);
        const fallback = merge(DEFAULT_LOCALE);
        const t: TranslateFn = (key, params) =>
            interpolate(table[key] ?? fallback[key] ?? key, params);
        return {locale, locales, setLocale, t};
    }, [overrides, locale, locales, setLocale]);

    // Tab title follows app.title, so a rename in custom/ messages applies too.
    useEffect(() => {
        document.title = value.t("app.title");
    }, [value]);

    return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
    const ctx = useContext(I18nContext);
    if (ctx == null) {
        throw new Error("useI18n must be used within I18nProvider");
    }
    return ctx;
}
