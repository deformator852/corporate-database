import {useEffect, useEffectEvent, useState} from "react";

import {useI18n} from "@/shared/i18n/I18nProvider";
import {useDebouncedSearch} from "@/shared/lib/hooks/useDebouncedSearch";
import {usePageParam} from "@/shared/lib/hooks/usePageParam";
import {useRequest} from "@/shared/lib/hooks/useRequest";
import {useUrlParams} from "@/shared/lib/hooks/useUrlParams";
import {can} from "@/shared/lib/api/me";
import {connectSocket} from "@/shared/lib/ws";
import {
    deleteDocument,
    documentsSocketUrl,
    getDocumentsPage,
} from "@pages/documents/api/documents";
import {
    allowedUploadClassifications,
    DOCUMENT_STATUS_FILTERS,
    DOCUMENTS_PER_PAGE,
    isDocumentUpdateNewer,
    isFiltered,
    type DocumentFilters,
    type DocumentStatusFilter,
    normalizeDocumentItem,
    type DocumentListItem,
    type DocumentListPage,
} from "@pages/documents/model/documents";
import {isDocumentStatus, type DocumentClassification} from "@/entities/document/model";
import {ConfirmDialog} from "@/shared/ui/ConfirmDialog";
import {DocumentFilterBar} from "@pages/documents/ui/DocumentFilterBar";
import {DocumentList} from "@pages/documents/ui/DocumentList";
import {DocumentUploadForm} from "@pages/documents/ui/DocumentUploadForm";

export function Documents() {
    const {t} = useI18n();
    const canCreate = can("documents.create");
    const canList = can("documents.list");
    const canDelete = can("documents.delete");
    const [page, goToPage] = usePageParam();
    const [params, updateParams] = useUrlParams();
    const classifications = allowedUploadClassifications(
        can("documents.restricted"),
        can("documents.confidential"),
        can("documents.secret"),
    );
    const filters = readFilters(params, classifications);
    const filtered = isFiltered(filters);
    const [search, setSearch] = useDebouncedSearch(filters.query, (query) => updateParams({q: query, page: "1"}));
    const {status, data, error, reload, update} = useRequest(
        canList ? `${page}:${filters.query}:${filters.status}:${filters.classification}` : null,
        () => getDocumentsPage(page, filters),
        t("documents.loadError"),
    );
    const [deleting, setDeleting] = useState<DocumentListItem | null>(null);

    const onDocumentEvent = useEffectEvent((raw: string) => {
        let payload: unknown;
        try {
            payload = JSON.parse(raw);
        } catch {
            return;
        }
        if (isDocumentEvent(payload)) {
            // A new document may not match the filters: only updates show then.
            update((current) => mergeDocument(current, normalizeDocumentItem(payload), filtered ? 0 : page));
        }
    });

    useEffect(() => {
        if (canList) {
            return connectSocket(documentsSocketUrl(), onDocumentEvent);
        }
    }, [canList]);

    return (
        <div className="stack stack--lg w-full">
            <div className="stack">
                <h1 id="documents-heading">{t("documents.title")}</h1>
                <p className="max-w-xl text-muted-foreground">
                    {t("documents.subtitle")}
                </p>
            </div>

            {canCreate ? (
                <div className="w-full rounded-xl bg-card p-4 ring-1 ring-foreground/10">
                    <DocumentUploadForm
                        onUploaded={(document) => {
                            update((current) =>
                                mergeDocument(current, normalizeDocumentItem(document), filtered ? 0 : page),
                            );
                        }}
                    />
                </div>
            ) : (
                <p className="text-sm text-muted-foreground">
                    {t("documents.noUploadPermission")}
                </p>
            )}

            {canList ? (
                <DocumentFilterBar
                    search={search}
                    onSearch={setSearch}
                    filters={filters}
                    classifications={classifications}
                    onChange={(changes) =>
                        updateParams({
                            status: changes.status ?? filters.status,
                            access: changes.classification ?? filters.classification,
                            page: "1",
                        })
                    }
                />
            ) : null}

            {canList ? (
                <DocumentList
                    headingId="documents-heading"
                    status={status}
                    error={error}
                    data={data}
                    page={page}
                    onRetry={reload}
                    filtered={filtered}
                    onClearFilters={() => updateParams({q: "", status: "", access: "", page: "1"})}
                    onPageChange={goToPage}
                    canDelete={canDelete}
                    onDelete={setDeleting}
                />
            ) : null}

            <ConfirmDialog
                open={deleting != null}
                onOpenChange={(open) => {
                    if (!open) {
                        setDeleting(null);
                    }
                }}
                title={t("documents.delete.title", {name: deleting?.name ?? t("common.thisDocument")})}
                description={t("documents.delete.description")}
                confirmLabel={t("common.delete")}
                pendingLabel={t("common.deleting")}
                errorMessage={t("documents.delete.error")}
                onConfirm={async () => {
                    if (!deleting) {
                        return;
                    }
                    await deleteDocument(deleting.id);
                    const items = data?.items ?? [];
                    if (items.length === 1 && page > 1) {
                        goToPage(page - 1);
                        return;
                    }
                    reload();
                }}
            />
        </div>
    );
}

function readFilters(params: URLSearchParams, classifications: DocumentClassification[]): DocumentFilters {
    const status = params.get("status") ?? "";
    const access = params.get("access") ?? "";
    return {
        query: params.get("q") ?? "",
        status: (DOCUMENT_STATUS_FILTERS as readonly string[]).includes(status) ? (status as DocumentStatusFilter) : "",
        classification: classifications.find((value) => value === access) ?? "",
    };
}

function isDocumentEvent(value: unknown): value is DocumentListItem {
    if (value == null || typeof value !== "object") {
        return false;
    }
    const item = value as Partial<DocumentListItem>;
    return (
        typeof item.id === "number" &&
        typeof item.name === "string" &&
        typeof item.filename === "string" &&
        typeof item.status === "string" &&
        isDocumentStatus(item.status) &&
        typeof item.progress === "number"
    );
}

function mergeDocument(current: DocumentListPage, incoming: DocumentListItem, page: number): DocumentListPage {
    const index = current.items.findIndex((item) => item.id === incoming.id);
    if (index >= 0) {
        if (!isDocumentUpdateNewer(incoming, current.items[index])) {
            return current;
        }
        const items = current.items.slice();
        items[index] = {...items[index], ...incoming};
        return {...current, items};
    }
    // A new document shows on the first page only.
    if (page !== 1) {
        return current;
    }
    return {...current, items: [incoming, ...current.items].slice(0, DOCUMENTS_PER_PAGE), total: current.total + 1};
}
