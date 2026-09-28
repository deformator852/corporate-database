import {useEffect, useMemo, useState} from "react";
import {useSearchParams} from "react-router";

import {Button} from "@/components/ui/button";
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
import {useI18n, type TranslateFn} from "@/shared/i18n/I18nProvider";
import {documentClassificationKey} from "@/shared/i18n/keys";
import {localeIntlTag} from "@/shared/i18n/messages";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import type {DocumentClassification} from "@pages/documents/model/documents";
import {getAuditPage} from "@pages/audit/api/audit";
import {
    AUDIT_ACTIONS,
    AUDIT_PER_PAGE,
    auditActionKey,
    isKnownAction,
    type AuditEntry,
    type AuditListPage,
} from "@pages/audit/model/audit";

const SEARCH_DEBOUNCE_MS = 300;

function parsePage(value: string | null): number {
    const page = Number(value);
    if (!Number.isInteger(page) || page < 1) {
        return 1;
    }
    return page;
}

function actionLabel(t: TranslateFn, action: string): string {
    return isKnownAction(action) ? t(auditActionKey(action)) : action;
}

function list(value: unknown): string[] {
    return Array.isArray(value) ? value.map(String) : [];
}

function accessLabel(t: TranslateFn, value: unknown): string {
    return t(documentClassificationKey(String(value) as DocumentClassification));
}

/** Short human summary of the structured `details` of an entry. */
function describe(t: TranslateFn, entry: AuditEntry): string {
    const {details} = entry;
    const parts: string[] = [];
    if (details.password_changed === true) {
        parts.push(t("audit.details.passwordChanged"));
    }
    const roles = list(details.roles);
    if (roles.length > 0) {
        parts.push(t("audit.details.roles", {value: roles.join(", ")}));
    }
    const permissions = list(details.permissions);
    if (permissions.length > 0) {
        parts.push(t("audit.details.permissions", {value: permissions.join(", ")}));
    }
    if (typeof details.classification === "string") {
        parts.push(t("audit.details.access", {value: accessLabel(t, details.classification)}));
    }
    if (Array.isArray(details.documents)) {
        const documents = details.documents as {name?: unknown; classification?: unknown}[];
        parts.push(
            documents
                .map((doc) => `${String(doc.name)} (${accessLabel(t, doc.classification)})`)
                .join(", "),
        );
    }
    return parts.join(" · ");
}

type LoadState =
    | {key: string; status: "ready"; data: AuditListPage}
    | {key: string; status: "error"; message: string};

export function AuditLog() {
    const {t, locale} = useI18n();
    const [searchParams, setSearchParams] = useSearchParams();
    const page = parsePage(searchParams.get("page"));
    const q = searchParams.get("q") ?? "";
    const action = searchParams.get("action") ?? "";
    const [draft, setDraft] = useState(q);
    const [reloadKey, setReloadKey] = useState(0);
    const requestKey = `${page}:${q}:${action}:${reloadKey}`;
    const [load, setLoad] = useState<LoadState | null>(null);

    const timeFormat = useMemo(
        () =>
            new Intl.DateTimeFormat(localeIntlTag(locale), {
                dateStyle: "short",
                timeStyle: "medium",
            }),
        [locale],
    );

    const updateParams = (changes: Record<string, string>) => {
        setSearchParams((current) => {
            const params = new URLSearchParams(current);
            for (const [name, value] of Object.entries(changes)) {
                if (!value || (name === "page" && value === "1")) {
                    params.delete(name);
                } else {
                    params.set(name, value);
                }
            }
            return params;
        });
    };

    useEffect(() => {
        const next = draft.trim();
        if (next === q) {
            return;
        }
        const timer = window.setTimeout(
            () => updateParams({q: next, page: "1"}),
            SEARCH_DEBOUNCE_MS,
        );
        return () => window.clearTimeout(timer);
        // updateParams only wraps the stable setSearchParams.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [draft, q]);

    useEffect(() => {
        let cancelled = false;

        void getAuditPage(page, q, action)
            .then((data) => {
                if (!cancelled) {
                    setLoad({key: requestKey, status: "ready", data});
                }
            })
            .catch((reason) => {
                if (!cancelled) {
                    setLoad({
                        key: requestKey,
                        status: "error",
                        message: getApiErrorMessage(reason, t("audit.loadError")),
                    });
                }
            });

        return () => {
            cancelled = true;
        };
    }, [page, q, action, requestKey, t]);

    const isCurrent = load?.key === requestKey;
    const status = !isCurrent ? "loading" : load.status;
    const data = isCurrent && load.status === "ready" ? load.data : null;
    const error = isCurrent && load.status === "error" ? load.message : null;
    const items = data?.items ?? [];
    const total = data?.total ?? 0;
    const pages = data?.pages ?? 0;
    const perPage = data?.per_page ?? AUDIT_PER_PAGE;
    const from = total === 0 ? 0 : (page - 1) * perPage + 1;
    const to = total === 0 ? 0 : (page - 1) * perPage + items.length;

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
                    <select
                        id="audit-action"
                        value={action}
                        onChange={(event) =>
                            updateParams({action: event.target.value, page: "1"})
                        }
                        className={cn(
                            "h-8 w-full min-w-0 cursor-pointer rounded-lg border border-input bg-transparent px-2.5 py-1 text-base outline-none transition-colors md:text-sm",
                            "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
                        )}
                    >
                        <option value="">{t("audit.allActions")}</option>
                        {AUDIT_ACTIONS.map((option) => (
                            <option key={option} value={option}>
                                {t(auditActionKey(option))}
                            </option>
                        ))}
                    </select>
                </div>
            </div>

            {status === "error" ? (
                <div className="flex flex-col items-start gap-3 rounded-xl bg-card px-4 py-8 ring-1 ring-foreground/10">
                    <p className="font-medium">{t("audit.loadErrorTitle")}</p>
                    <p className="text-sm text-muted-foreground">{error}</p>
                    <Button type="button" onClick={() => setReloadKey((key) => key + 1)}>
                        {t("common.tryAgain")}
                    </Button>
                </div>
            ) : status === "ready" && total === 0 ? (
                <div className="flex flex-col items-start gap-3 rounded-xl bg-card px-4 py-8 ring-1 ring-foreground/10">
                    <p className="font-medium">{t("audit.emptyTitle")}</p>
                </div>
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
                                                    {entry.actor_email ?? t("common.noDataDash")}
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
                                                <TableCell
                                                    className="max-w-sm truncate text-muted-foreground"
                                                    title={details || undefined}
                                                >
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

                    {status === "ready" ? (
                        <nav
                            aria-label={t("common.pagination")}
                            className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
                        >
                            <p className="text-sm text-muted-foreground">
                                {t("common.showing", {from, to, total})}
                            </p>
                            <div className="flex items-center gap-2">
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    disabled={page <= 1}
                                    onClick={() => updateParams({page: String(page - 1)})}
                                >
                                    {t("common.previous")}
                                </Button>
                                <p className="min-w-24 text-center text-sm text-muted-foreground">
                                    {t("common.pageOf", {page, pages: Math.max(pages, 1)})}
                                </p>
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    disabled={pages === 0 || page >= pages}
                                    onClick={() => updateParams({page: String(page + 1)})}
                                >
                                    {t("common.next")}
                                </Button>
                            </div>
                        </nav>
                    ) : null}
                </div>
            )}
        </div>
    );
}
