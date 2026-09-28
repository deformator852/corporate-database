import {Check, Languages} from "lucide-react";
import {useState} from "react";

import {Button} from "@/components/ui/button";
import {Popover, PopoverContent, PopoverTrigger} from "@/components/ui/popover";

import {useI18n} from "./I18nProvider";
import {LOCALES, type Locale} from "./messages";

const LOCALE_LABEL_KEYS: Record<Locale, `language.${Locale}`> = {
    en: "language.en",
    es: "language.es",
    uk: "language.uk",
    tr: "language.tr",
    fr: "language.fr",
};

export function LanguageSwitcher() {
    const {locale, setLocale, t} = useI18n();
    const [open, setOpen] = useState(false);

    const currentLabel = t(LOCALE_LABEL_KEYS[locale]);

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger
                render={
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={`${t("language.label")}: ${currentLabel}`}
                    />
                }
            >
                <Languages />
            </PopoverTrigger>
            <PopoverContent className="w-48 p-1" aria-label={t("language.label")}>
                <div
                    role="radiogroup"
                    aria-label={t("language.label")}
                    className="flex flex-col"
                >
                    {LOCALES.map((option) => {
                        const selected = locale === option;
                        return (
                            <button
                                key={option}
                                type="button"
                                role="radio"
                                aria-checked={selected}
                                className="flex cursor-pointer items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm outline-none hover:bg-muted focus-visible:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
                                onClick={() => {
                                    setLocale(option);
                                    setOpen(false);
                                }}
                            >
                                {t(LOCALE_LABEL_KEYS[option])}
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
