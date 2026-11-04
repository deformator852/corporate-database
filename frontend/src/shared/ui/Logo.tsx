import {cn} from "cn";

import {useI18n} from "@/shared/i18n/I18nProvider";

/**
 * Corpus mark: a "C" holding a paragraph of three lines (two would read
 * as a euro sign at 16px). The tile takes the theme's
 * primary color, so it follows every theme; public/favicon.svg is the same
 * drawing in the fixed brand color.
 */
export function LogoMark({className}: {className?: string}) {
    return (
        <span
            className={cn(
                "inline-flex shrink-0 items-center justify-center rounded-[25%] bg-primary text-primary-content",
                className,
            )}
            aria-hidden
        >
            <svg viewBox="0 0 32 32" className="size-full" fill="none">
                <path
                    d="M22.6 10a8.6 8.6 0 1 0 0 12"
                    stroke="currentColor"
                    strokeWidth="3.6"
                    strokeLinecap="round"
                />
                <g fill="currentColor" opacity=".85">
                    <rect x="14.4" y="11.45" width="8.2" height="2.1" rx="1.05" />
                    <rect x="14.4" y="14.95" width="8.2" height="2.1" rx="1.05" />
                    <rect x="14.4" y="18.45" width="5.2" height="2.1" rx="1.05" />
                </g>
            </svg>
        </span>
    );
}

/** Mark and product name, for the header. */
export function Logo({className}: {className?: string}) {
    const {t} = useI18n();
    return (
        <span className={cn("flex min-w-0 items-center gap-2.5", className)}>
            <LogoMark className="size-8" />
            <span className="truncate text-[15px] font-semibold tracking-tight">
                {t("app.title")}
            </span>
        </span>
    );
}
