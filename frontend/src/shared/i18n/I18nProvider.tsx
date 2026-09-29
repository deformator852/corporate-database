import {createContext, useContext, useEffect, useMemo, type ReactNode} from "react";

import {
    DEFAULT_LOCALE,
    LOCALE,
    localeHtmlLang,
    messages,
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
    t: TranslateFn;
};

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

export function I18nProvider({
    children,
    overrides = [],
}: {
    children: ReactNode;
    overrides?: MessageOverrides[];
}) {
    useEffect(() => {
        document.documentElement.lang = localeHtmlLang(LOCALE);
    }, []);

    const value = useMemo(() => {
        const merge = (locale: Locale): Record<string, string> =>
            Object.assign({}, messages[locale], ...overrides.map((o) => o[locale]));
        const table = merge(LOCALE);
        const fallback = merge(DEFAULT_LOCALE);
        const t: TranslateFn = (key, params) =>
            interpolate(table[key] ?? fallback[key] ?? key, params);
        return {locale: LOCALE, t};
    }, [overrides]);

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
