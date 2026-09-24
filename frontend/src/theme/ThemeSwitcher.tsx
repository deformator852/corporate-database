import {Check, Palette} from "lucide-react";
import {useState} from "react";

import {Button} from "@/components/ui/button";
import {Popover, PopoverContent, PopoverTrigger} from "@/components/ui/popover";

import {isTheme, THEME_LABELS, THEMES} from "./themes";
import {useTheme} from "./ThemeProvider";

export function ThemeSwitcher() {
    const {theme, setTheme} = useTheme();
    const [open, setOpen] = useState(false);

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger
                render={
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={`Theme: ${THEME_LABELS[theme]}`}
                    />
                }
            >
                <Palette />
            </PopoverTrigger>
            <PopoverContent className="w-44 p-1" aria-label="Theme">
                <div role="radiogroup" aria-label="Theme" className="flex flex-col">
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
                                {THEME_LABELS[option]}
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
