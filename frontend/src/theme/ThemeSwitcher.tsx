import {Moon, Palette, Sun} from "lucide-react";

import {Button} from "@/components/ui/button";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {ChoiceMenu} from "@/shared/ui/ChoiceMenu";

import {findTheme, THEMES} from "./themes";
import {useTheme} from "./ThemeProvider";

/** A light/dark button for the two core themes; a menu once extensions add more. */
export function ThemeSwitcher() {
    const {t} = useI18n();
    const {theme, setTheme} = useTheme();

    if (THEMES.length === 2) {
        const next = THEMES[theme.id === THEMES[0].id ? 1 : 0];
        const label = t(next.dark ? "theme.toDark" : "theme.toLight");
        return (
            <Button type="button" variant="ghost" size="icon" aria-label={label} title={label} onClick={() => setTheme(next)}>
                {next.dark ? <Moon aria-hidden /> : <Sun aria-hidden />}
            </Button>
        );
    }

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
