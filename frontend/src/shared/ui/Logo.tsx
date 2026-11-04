import {cn} from "cn";

import {useI18n} from "@/shared/i18n/I18nProvider";

/**
 * Archfold mark: a ribbon folded into an "A". The tile takes the theme's primary
 * color, unless the theme sets --logo-tile and --logo-mark; public/favicon.svg is
 * the same drawing in the fixed brand color.
 */
export function LogoMark({className}: {className?: string}) {
    return (
        <span
            className={cn(
                "inline-flex shrink-0 items-center justify-center rounded-[25%] bg-[var(--logo-tile,var(--color-primary))] text-[color:var(--logo-mark,var(--color-primary-content))]",
                className,
            )}
            aria-hidden
        >
            <svg viewBox="0 0 32 32" className="size-full" fill="currentColor">
                <path d="M5 27 13 6h3v8.5L11 27Z" />
                <path d="M16 6h3l8 21h-6l-5-12.5Z" opacity=".6" />
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
