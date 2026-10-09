import {Palette} from "lucide-react";

import {useI18n} from "@/shared/i18n/I18nProvider";
import {ChoiceMenu} from "@/shared/ui/ChoiceMenu";

import {findTheme, THEMES} from "./themes";
import {useTheme} from "./ThemeProvider";

export function ThemeSwitcher() {
    const {t} = useI18n();
    const {theme, setTheme} = useTheme();

    return (
        <ChoiceMenu
            icon={<Palette />}
            label={t("theme.label")}
            choices={THEMES.map((option) => ({value: option.id, label: t(option.labelKey)}))}
            value={theme.id}
            onChange={(id) => {
                const next = findTheme(id);
                if (next) {
                    setTheme(next);
                }
            }}
        />
    );
}
