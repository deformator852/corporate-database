import type {ReactNode} from "react";

/** A page's title and what it is for; `action` (a button, a filter) sits on
 * the right on wide screens. `id` lets a table name itself after the title. */
export function PageHeader({
    title,
    subtitle,
    id,
    action,
}: {
    title: ReactNode;
    subtitle: ReactNode;
    id?: string;
    action?: ReactNode;
}) {
    const text = (
        <div className="stack">
            <h1 id={id}>{title}</h1>
            <p className="max-w-xl text-base-content/70">{subtitle}</p>
        </div>
    );
    if (action == null) {
        return text;
    }
    return (
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            {text}
            {action}
        </div>
    );
}
