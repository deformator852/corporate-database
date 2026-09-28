import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useState,
    type ReactNode,
} from "react";

import {
    DEFAULT_LOCALE,
    isLocale,
    LOCALE_STORAGE_KEY,
    localeHtmlLang,
    messages,
    type Locale,
    type MessageKey,
} from "./messages";

export type TranslateFn = (key: MessageKey, params?: Record<string, string | number>) => string;

type I18nContextValue = {
    locale: Locale;
    setLocale: (locale: Locale) => void;
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

function readStoredLocale(): Locale {
    try {
        const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
        if (stored === "ja") {
            return DEFAULT_LOCALE;
        }
        if (isLocale(stored)) {
            return stored;
        }
    } catch {
        // ignore
    }
    return DEFAULT_LOCALE;
}

export function I18nProvider({children}: {children: ReactNode}) {
    const [locale, setLocaleState] = useState<Locale>(() => readStoredLocale());

    const setLocale = useCallback((next: Locale) => {
        setLocaleState(next);
        try {
            localStorage.setItem(LOCALE_STORAGE_KEY, next);
        } catch {
            // ignore
        }
    }, []);

    useEffect(() => {
        document.documentElement.lang = localeHtmlLang(locale);
    }, [locale]);

    const t = useCallback<TranslateFn>(
        (key, params) => {
            const table = messages[locale];
            const fallback = messages[DEFAULT_LOCALE];
            const template = table[key] ?? fallback[key] ?? key;
            return interpolate(template, params);
        },
        [locale],
    );

    const value = useMemo(
        () => ({
            locale,
            setLocale,
            t,
        }),
        [locale, setLocale, t],
    );

    return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
    const ctx = useContext(I18nContext);
    if (ctx == null) {
        throw new Error("useI18n must be used within I18nProvider");
    }
    return ctx;
}
