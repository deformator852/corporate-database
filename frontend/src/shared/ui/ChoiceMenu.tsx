import {Check} from "lucide-react";
import {useState, type ReactNode} from "react";

import {Button} from "@/components/ui/button";
import {Popover, PopoverContent, PopoverTrigger} from "@/components/ui/popover";

export type Choice<T extends string> = {
    value: T;
    label: string;
    /** The label's language, when it is not the page's. */
    lang?: string;
};

/** An icon button in the header that opens a list to pick one of `choices`. */
export function ChoiceMenu<T extends string>({
    icon,
    label,
    choices,
    value,
    onChange,
}: {
    icon: ReactNode;
    label: string;
    choices: Choice<T>[];
    value: T;
    onChange: (value: T) => void;
}) {
    const [open, setOpen] = useState(false);
    const current = choices.find((choice) => choice.value === value);

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger
                render={
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={current ? `${label}: ${current.label}` : label}
                    />
                }
            >
                {icon}
            </PopoverTrigger>
            <PopoverContent className="w-44 p-1" aria-label={label}>
                <div role="radiogroup" aria-label={label} className="flex flex-col">
                    {choices.map((choice) => (
                        <button
                            key={choice.value}
                            type="button"
                            role="radio"
                            aria-checked={choice.value === value}
                            lang={choice.lang}
                            className="flex cursor-pointer items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm outline-none hover:bg-muted focus-visible:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
                            onClick={() => {
                                onChange(choice.value);
                                setOpen(false);
                            }}
                        >
                            {choice.label}
                            {choice.value === value ? <Check className="size-4" aria-hidden /> : null}
                        </button>
                    ))}
                </div>
            </PopoverContent>
        </Popover>
    );
}
