import {Languages} from "lucide-react";
import {useEffect, useEffectEvent} from "react";

import {useSessionStore} from "@/shared/auth/session-store";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {isLocale, LOCALE_NAMES} from "@/shared/i18n/messages";
import {saveLanguage} from "@/shared/lib/api/me";
import {ChoiceMenu} from "@/shared/ui/ChoiceMenu";

/** The languages of APP_LANGUAGES; hidden when only one is enabled. The
 * choice is saved on the account: the server writes errors, notices and
 * answers in it, on every device. */
export function LanguageSwitcher() {
    const {t, locale, locales, setLocale} = useI18n();
    const user = useSessionStore((state) => state.user);

    // On sign-in: the account's language wins; an account without one
    // takes the language already shown.
    const adopt = useEffectEvent(() => {
        const saved = user?.language;
        if (isLocale(saved) && locales.includes(saved)) {
            setLocale(saved);
        } else if (locales.length > 1) {
            void saveLanguage(locale).catch(() => undefined);
        }
    });
    // Only when another user signs in: later changes are made here.
    const userId = user?.id;
    useEffect(() => {
        if (userId !== undefined) {
            adopt();
        }
    }, [userId]);

    if (locales.length < 2) {
        return null;
    }

    return (
        <ChoiceMenu
            icon={<Languages />}
            label={t("language.label")}
            choices={locales.map((code) => ({value: code, label: LOCALE_NAMES[code], lang: code}))}
            value={locale}
            onChange={(next) => {
                setLocale(next);
                void saveLanguage(next).catch(() => undefined);
            }}
        />
    );
}
