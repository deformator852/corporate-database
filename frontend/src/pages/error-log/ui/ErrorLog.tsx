import {useMemo} from "react";

import {Card} from "@/components/ui/card";
import {NativeSelect, NativeSelectOption} from "@/components/ui/native-select";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {PageHeader} from "@/shared/ui/PageHeader";
import {localeIntlTag} from "@/shared/i18n/messages";
import {usePageParam} from "@/shared/lib/hooks/usePageParam";
import {useRequest} from "@/shared/lib/hooks/useRequest";
import {useUrlParams} from "@/shared/lib/hooks/useUrlParams";
import {ListPagination} from "@/shared/ui/ListPagination";
import {StatusCard} from "@/shared/ui/StatusCard";
import {cn} from "cn";
import {getErrorLogPage} from "@pages/error-log/api/errorLog";
import {
    ERROR_CATEGORIES,
    ERROR_LEVELS,
    categoryKey,
    levelKey,
    type ErrorLogEntry,
    type ErrorLogFilters,
} from "@pages/error-log/model/errorLog";

/** Warnings and errors of the backend and the worker, newest first, with
 * their tracebacks. */
export function ErrorLog() {
    const {t} = useI18n();
    const [params, updateParams] = useUrlParams();
    const [page, goToPage] = usePageParam();
    const filters: ErrorLogFilters = {
        level: known(ERROR_LEVELS, params.get("level")),
        category: known(ERROR_CATEGORIES, params.get("category")),
    };
    const {status, data, error, reload} = useRequest(
        `${page}:${filters.level}:${filters.category}`,
        () => getErrorLogPage(page, filters),
        t("errorLog.loadError"),
    );
    const items = data?.items ?? [];
    const choose = (name: keyof ErrorLogFilters) => (value: string) => updateParams({[name]: value, page: "1"});

    return (
        <div className="stack stack--lg w-full">
            <PageHeader title={t("errorLog.title")} subtitle={t("errorLog.subtitle")} />

            <div className="flex flex-col gap-3 sm:flex-row">
                <Filter
                    label={t("errorLog.filterCategory")}
                    all={t("errorLog.allCategories")}
                    values={ERROR_CATEGORIES}
                    labelOf={(value) => t(categoryKey(value))}
                    value={filters.category}
                    onChange={choose("category")}
                />
                <Filter
                    label={t("errorLog.filterLevel")}
                    all={t("errorLog.allLevels")}
                    values={ERROR_LEVELS}
                    labelOf={(value) => t(levelKey(value))}
                    value={filters.level}
                    onChange={choose("level")}
                />
            </div>

            {status === "error" ? (
                <StatusCard title={t("errorLog.loadErrorTitle")} detail={error} onRetry={reload} />
            ) : status === "loading" ? (
                <p className="text-sm text-muted-foreground">{t("errorLog.loading")}</p>
            ) : items.length === 0 ? (
                <StatusCard title={t("errorLog.empty")} detail={t("errorLog.emptyHint")} />
            ) : (
                <div className="stack">
                    <ul className="flex list-none flex-col gap-2 ps-0">
                        {items.map((entry) => (
                            <li key={entry.id}>
                                <ErrorEntry entry={entry} />
                            </li>
                        ))}
                    </ul>
                    {data ? (
                        <ListPagination
                            page={page}
                            pages={data.pages}
                            perPage={data.per_page}
                            total={data.total}
                            shown={items.length}
                            onPageChange={goToPage}
                        />
                    ) : null}
                </div>
            )}
        </div>
    );
}

/** `value` when it is one of `values`; anything else means no filter. */
function known(values: readonly string[], value: string | null): string {
    return value != null && values.includes(value) ? value : "";
}

function Filter({
    label,
    all,
    values,
    labelOf,
    value,
    onChange,
}: {
    label: string;
    all: string;
    values: readonly string[];
    labelOf: (value: string) => string;
    value: string;
    onChange: (value: string) => void;
}) {
    return (
        <NativeSelect className="w-full sm:w-56" aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}>
            <NativeSelectOption value="">{all}</NativeSelectOption>
            {values.map((option) => (
                <NativeSelectOption key={option} value={option}>
                    {labelOf(option)}
                </NativeSelectOption>
            ))}
        </NativeSelect>
    );
}

// Unhandled errors are bugs to look at first: they stand out.
const CATEGORY_STYLE: Record<string, string> = {
    unhandled: "border border-destructive/40 text-destructive",
    app: "border border-border",
    library: "border border-dashed border-border",
};

const LEVEL_STYLE: Record<string, string> = {
    warning: "bg-amber-100 text-amber-900 dark:bg-amber-500/20 dark:text-amber-100",
    error: "bg-destructive/10 text-destructive",
    critical: "bg-destructive text-white",
};

function ErrorEntry({entry}: {entry: ErrorLogEntry}) {
    const {t, locale} = useI18n();
    const time = useMemo(
        () => new Intl.DateTimeFormat(localeIntlTag(locale), {dateStyle: "short", timeStyle: "medium"}),
        [locale],
    );
    return (
        <Card className="gap-2 px-4 py-3">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <span className={cn("rounded-full px-2 py-0.5 font-medium", LEVEL_STYLE[entry.level])}>
                    {t(levelKey(entry.level))}
                </span>
                <span className={cn("rounded-full px-2 py-0.5", CATEGORY_STYLE[entry.category])}>
                    {t(categoryKey(entry.category))}
                </span>
                <span className="font-mono">{entry.logger}</span>
                <time dateTime={entry.created_at} className="tabular-nums">
                    {time.format(new Date(entry.created_at))}
                </time>
            </div>
            <p className="text-sm font-medium break-words whitespace-pre-wrap">{entry.message}</p>
            {entry.traceback ? (
                <details className="text-sm">
                    <summary className="cursor-pointer text-muted-foreground select-none hover:text-foreground">
                        {t("errorLog.traceback")}
                    </summary>
                    <pre className="mt-2 max-h-96 overflow-auto rounded-lg bg-muted p-3 font-mono text-xs leading-relaxed">
                        {entry.traceback}
                    </pre>
                </details>
            ) : null}
        </Card>
    );
}
