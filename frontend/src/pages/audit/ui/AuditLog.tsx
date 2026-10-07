import {useMemo} from "react";
import {Link, useLocation} from "react-router";

import {Card} from "@/components/ui/card";
import {Input} from "@/components/ui/input";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {cn} from "cn";
import {NativeSelect} from "@/components/ui/native-select";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {useDebouncedSearch} from "@/shared/lib/hooks/useDebouncedSearch";
import {useUrlParams} from "@/shared/lib/hooks/useUrlParams";
import {usePageParam} from "@/shared/lib/hooks/usePageParam";
import {useRequest} from "@/shared/lib/hooks/useRequest";
import {ListPagination} from "@/shared/ui/ListPagination";
import {StatusCard} from "@/shared/ui/StatusCard";
import {localeIntlTag} from "@/shared/i18n/messages";
import {can} from "@/shared/lib/api/me";
import {getAuditPage} from "@pages/audit/api/audit";
import {AUDIT_ACTIONS, auditActionKey} from "@/entities/audit/model";
import {actionLabel, describe} from "@/entities/audit/format";
import type {UserDetailLinkState} from "@/entities/user/model";


export function AuditLog() {
    const {t, locale} = useI18n();
    const [searchParams, updateParams] = useUrlParams();
    const [page] = usePageParam();
    const q = searchParams.get("q") ?? "";
    const action = searchParams.get("action") ?? "";
    const [draft, setDraft] = useDebouncedSearch(q, (next) => updateParams({q: next, page: "1"}));

    const timeFormat = useMemo(
        () =>
            new Intl.DateTimeFormat(localeIntlTag(locale), {
                dateStyle: "short",
                timeStyle: "medium",
            }),
        [locale],
    );


    const {status, data, error, reload} = useRequest(
        `${page}:${q}:${action}`,
        () => getAuditPage(page, q, action),
        t("audit.loadError"),
    );
    const items = data?.items ?? [];
    const total = data?.total ?? 0;
    const canOpenUser = can("users.view");
    const location = useLocation();
    // The user page's Back link returns here with the same filters.
    const linkState: UserDetailLinkState = {from: location.pathname + location.search};

    return (
        <div className="stack stack--lg w-full">
            <div className="stack">
                <h1 id="audit-heading">{t("audit.title")}</h1>
                <p className="max-w-xl text-muted-foreground">{t("audit.subtitle")}</p>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                    <label htmlFor="audit-search" className="text-sm font-medium">
                        {t("audit.search")}
                    </label>
                    <Input
                        id="audit-search"
                        type="search"
                        value={draft}
                        maxLength={100}
                        onChange={(event) => setDraft(event.target.value)}
                    />
                </div>
                <div className="flex flex-col gap-1.5 sm:w-64">
                    <label htmlFor="audit-action" className="text-sm font-medium">
                        {t("audit.filterAction")}
                    </label>
                    <NativeSelect
                        id="audit-action"
                        className="w-full"
                        value={action}
                        onChange={(event) => updateParams({action: event.target.value, page: "1"})}
                    >
                        <option value="">{t("audit.allActions")}</option>
                        {AUDIT_ACTIONS.map((option) => (
                            <option key={option} value={option}>
                                {t(auditActionKey(option))}
                            </option>
                        ))}
                    </NativeSelect>
                </div>
            </div>

            {status === "error" ? (
                <StatusCard title={t("audit.loadErrorTitle")} detail={error} onRetry={reload} />
            ) : status === "ready" && total === 0 ? (
                <StatusCard title={t("audit.emptyTitle")} />
            ) : (
                <div className="stack">
                    <Card className="gap-0 py-0">
                        <Table aria-labelledby="audit-heading">
                            <TableHeader>
                                <TableRow className="hover:bg-transparent">
                                    <TableHead className="px-4">{t("audit.table.time")}</TableHead>
                                    <TableHead>{t("audit.table.user")}</TableHead>
                                    <TableHead>{t("audit.table.action")}</TableHead>
                                    <TableHead>{t("audit.table.target")}</TableHead>
                                    <TableHead>{t("audit.table.details")}</TableHead>
                                    <TableHead className="px-4">{t("audit.table.ip")}</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {status === "loading" ? (
                                    <TableRow className="hover:bg-transparent">
                                        <TableCell
                                            colSpan={6}
                                            className="px-4 py-8 text-muted-foreground"
                                        >
                                            {t("audit.loading")}
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    items.map((entry) => {
                                        const details = describe(t, entry);
                                        return (
                                            <TableRow key={entry.id}>
                                                <TableCell className="px-4 whitespace-nowrap text-muted-foreground tabular-nums">
                                                    {timeFormat.format(new Date(entry.created_at))}
                                                </TableCell>
                                                <TableCell className="max-w-48 truncate">
                                                    {canOpenUser && entry.actor_id != null ? (
                                                        <Link
                                                            to={`/users/${entry.actor_id}`}
                                                            state={linkState}
                                                            className="font-medium underline-offset-4 hover:underline"
                                                            aria-label={t("userDetail.openAria", {
                                                                name: entry.actor_email ?? "",
                                                            })}
                                                        >
                                                            {entry.actor_email}
                                                        </Link>
                                                    ) : (
                                                        entry.actor_email ?? t("common.noDataDash")
                                                    )}
                                                </TableCell>
                                                <TableCell
                                                    className={cn(
                                                        "whitespace-nowrap font-medium",
                                                        entry.action === "auth.login_failed" &&
                                                            "text-destructive",
                                                    )}
                                                >
                                                    {actionLabel(t, entry.action)}
                                                </TableCell>
                                                <TableCell className="max-w-48 truncate">
                                                    {entry.target_label ?? t("common.noDataDash")}
                                                </TableCell>
                                                <TableCell className="min-w-48 whitespace-normal text-muted-foreground">
                                                    {details || t("common.noDataDash")}
                                                </TableCell>
                                                <TableCell className="px-4 whitespace-nowrap text-muted-foreground tabular-nums">
                                                    {entry.ip ?? t("common.noDataDash")}
                                                </TableCell>
                                            </TableRow>
                                        );
                                    })
                                )}
                            </TableBody>
                        </Table>
                    </Card>

                    {data ? (
                        <ListPagination
                            page={page}
                            pages={data.pages}
                            perPage={data.per_page}
                            total={total}
                            shown={items.length}
                            onPageChange={(next) => updateParams({page: String(next)})}
                        />
                    ) : null}
                </div>
            )}
        </div>
    );
}
