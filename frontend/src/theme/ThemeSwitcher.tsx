import {Check, Palette} from "lucide-react";
import {useState} from "react";

import {Button} from "@/components/ui/button";
import {Popover, PopoverContent, PopoverTrigger} from "@/components/ui/popover";
import {useI18n} from "@/shared/i18n/I18nProvider";
import type {MessageKey} from "@/shared/i18n/messages";

import {isTheme, THEMES, type Theme} from "./themes";
import {useTheme} from "./ThemeProvider";

const THEME_LABEL_KEYS: Record<Theme, MessageKey> = {
    neutral: "theme.neutral",
    slate: "theme.slate",
};

export function ThemeSwitcher() {
    const {t} = useI18n();
    const {theme, setTheme} = useTheme();
    const [open, setOpen] = useState(false);
    const currentLabel = t(THEME_LABEL_KEYS[theme]);

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger
                render={
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={`${t("theme.label")}: ${currentLabel}`}
                    />
                }
            >
                <Palette />
            </PopoverTrigger>
            <PopoverContent className="w-44 p-1" aria-label={t("theme.label")}>
                <div role="radiogroup" aria-label={t("theme.label")} className="flex flex-col">
                    {THEMES.map((option) => {
                        const selected = theme === option;
                        return (
                            <button
                                key={option}
                                type="button"
                                role="radio"
                                aria-checked={selected}
                                className="flex cursor-pointer items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm outline-none hover:bg-muted focus-visible:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
                                onClick={() => {
                                    if (isTheme(option)) {
                                        setTheme(option);
                                    }
                                    setOpen(false);
                                }}
                            >
                                {t(THEME_LABEL_KEYS[option])}
                                {selected ? (
                                    <Check className="size-4" aria-hidden />
                                ) : null}
                            </button>
                        );
                    })}
                </div>
            </PopoverContent>
        </Popover>
    );
}
