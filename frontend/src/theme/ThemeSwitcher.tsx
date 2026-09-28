import {Check, Palette} from "lucide-react";
import {useState} from "react";

import {Button} from "@/components/ui/button";
import {Popover, PopoverContent, PopoverTrigger} from "@/components/ui/popover";
import {useI18n} from "@/shared/i18n/I18nProvider";

import {THEMES} from "./themes";
import {useTheme} from "./ThemeProvider";

export function ThemeSwitcher() {
    const {t} = useI18n();
    const {theme, setTheme} = useTheme();
    const [open, setOpen] = useState(false);
    const currentLabel = t(theme.labelKey);

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
                        const selected = theme.id === option.id;
                        return (
                            <button
                                key={option.id}
                                type="button"
                                role="radio"
                                aria-checked={selected}
                                className="flex cursor-pointer items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm outline-none hover:bg-muted focus-visible:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
                                onClick={() => {
                                    setTheme(option);
                                    setOpen(false);
                                }}
                            >
                                {t(option.labelKey)}
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
