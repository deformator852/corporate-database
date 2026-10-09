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
    ERROR_LEVELS,
    ERROR_SOURCES,
    levelKey,
    sourceKey,
    type ErrorLogEntry,
} from "@pages/error-log/model/errorLog";

/** Warnings and errors of the backend and the worker, newest first, with
 * their tracebacks. */
export function ErrorLog() {
    const {t} = useI18n();
    const [params, updateParams] = useUrlParams();
    const [page, goToPage] = usePageParam();
    const level = (ERROR_LEVELS as readonly string[]).includes(params.get("level") ?? "") ? params.get("level")! : "";
    const source = (ERROR_SOURCES as readonly string[]).includes(params.get("source") ?? "") ? params.get("source")! : "";
    const {status, data, error, reload} = useRequest(
        `${page}:${level}:${source}`,
        () => getErrorLogPage(page, level, source),
        t("errorLog.loadError"),
    );
    const items = data?.items ?? [];

    return (
        <div className="stack stack--lg w-full">
            <PageHeader title={t("errorLog.title")} subtitle={t("errorLog.subtitle")} />

            <div className="flex flex-col gap-3 sm:flex-row">
                <NativeSelect
                    className="w-full sm:w-56"
                    aria-label={t("errorLog.filterLevel")}
                    value={level}
                    onChange={(event) => updateParams({level: event.target.value, page: "1"})}
                >
                    <NativeSelectOption value="">{t("errorLog.allLevels")}</NativeSelectOption>
                    {ERROR_LEVELS.map((value) => (
                        <NativeSelectOption key={value} value={value}>
                            {t(levelKey(value))}
                        </NativeSelectOption>
                    ))}
                </NativeSelect>
                <NativeSelect
                    className="w-full sm:w-56"
                    aria-label={t("errorLog.filterSource")}
                    value={source}
                    onChange={(event) => updateParams({source: event.target.value, page: "1"})}
                >
                    <NativeSelectOption value="">{t("errorLog.allSources")}</NativeSelectOption>
                    {ERROR_SOURCES.map((value) => (
                        <NativeSelectOption key={value} value={value}>
                            {t(sourceKey(value))}
                        </NativeSelectOption>
                    ))}
                </NativeSelect>
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
                <span>{t(sourceKey(entry.source))}</span>
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
