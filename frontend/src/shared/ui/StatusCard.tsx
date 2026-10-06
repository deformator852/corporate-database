import type {ReactNode} from "react";

import {Button} from "@/components/ui/button";
import {useI18n} from "@/shared/i18n/I18nProvider";

type StatusCardProps = {
    title: string;
    detail?: ReactNode;
    /** Shows a "Try again" button. */
    onRetry?: () => void;
    children?: ReactNode;
};

/** In place of a list: why it failed to load, or that it is empty. */
export function StatusCard({title, detail, onRetry, children}: StatusCardProps) {
    const {t} = useI18n();
    return (
        <div className="flex flex-col items-start gap-3 rounded-xl bg-card px-4 py-8 ring-1 ring-foreground/10">
            <p className="font-medium">{title}</p>
            {detail ? <p className="text-sm text-muted-foreground">{detail}</p> : null}
            {onRetry ? (
                <Button type="button" onClick={onRetry}>
                    {t("common.tryAgain")}
                </Button>
            ) : null}
            {children}
        </div>
    );
}
