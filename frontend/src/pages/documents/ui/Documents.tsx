import {useEffect, useState} from "react";
import {useSearchParams} from "react-router";

import {useI18n} from "@/shared/i18n/I18nProvider";
import {can} from "@/shared/lib/api/me";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {connectSocket} from "@/shared/lib/ws";
import {
    deleteDocument,
    documentsSocketUrl,
    getDocumentsPage,
} from "@pages/documents/api/documents";
import {
    DOCUMENTS_PER_PAGE,
    isDocumentStatus,
    isDocumentUpdateNewer,
    normalizeDocumentItem,
    type DocumentListItem,
    type DocumentListPage,
} from "@pages/documents/model/documents";
import {ConfirmDialog} from "@/shared/ui/ConfirmDialog";
import {DocumentList} from "@pages/documents/ui/DocumentList";
import {DocumentUploadForm} from "@pages/documents/ui/DocumentUploadForm";

function parsePage(value: string | null): number {
    const page = Number(value);
    if (!Number.isInteger(page) || page < 1) {
        return 1;
    }
    return page;
}

type LoadState =
    | {key: string; status: "ready"; data: DocumentListPage}
    | {key: string; status: "error"; message: string};

export function Documents() {
    const {t} = useI18n();
    const canCreate = can("documents.create");
    const canList = can("documents.list");
    const canDelete = can("documents.delete");
    const [searchParams, setSearchParams] = useSearchParams();
    const page = parsePage(searchParams.get("page"));
    const [reloadKey, setReloadKey] = useState(0);
    const requestKey = `${page}:${reloadKey}`;
    const [load, setLoad] = useState<LoadState | null>(null);
    const [deleting, setDeleting] = useState<DocumentListItem | null>(null);

    useEffect(() => {
        if (!canList) {
            return;
        }
        let cancelled = false;
        void getDocumentsPage(page)
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
                        message: getApiErrorMessage(
                            reason,
                            t("documents.loadError"),
                        ),
                    });
                }
            });
        return () => {
            cancelled = true;
        };
    }, [canList, page, reloadKey, requestKey]);

    useEffect(() => {
        if (!canList) {
            return;
        }
        return connectSocket(documentsSocketUrl(), (raw) => {
            let payload: unknown;
            try {
                payload = JSON.parse(raw);
            } catch {
                return;
            }
            if (!isDocumentEvent(payload)) {
                return;
            }
            setLoad((current) =>
                mergeDocument(current, normalizeDocumentItem(payload), page),
            );
        });
    }, [canList, page]);

    const goToPage = (nextPage: number) => {
        setSearchParams((current) => {
            const params = new URLSearchParams(current);
            if (nextPage <= 1) {
                params.delete("page");
            } else {
                params.set("page", String(nextPage));
            }
            return params;
        });
    };

    const isCurrent = load?.key === requestKey;
    const listStatus = !canList
        ? "ready"
        : !isCurrent
          ? "loading"
          : load.status;
    const data = isCurrent && load.status === "ready" ? load.data : null;
    const error = isCurrent && load.status === "error" ? load.message : null;

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
                            setLoad((current) =>
                                mergeDocument(
                                    current,
                                    normalizeDocumentItem(document),
                                    page,
                                ),
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
                <DocumentList
                    headingId="documents-heading"
                    status={listStatus}
                    error={error}
                    data={data}
                    page={page}
                    onRetry={() => setReloadKey((key) => key + 1)}
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
                    setReloadKey((key) => key + 1);
                }}
            />
        </div>
    );
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

function mergeDocument(
    current: LoadState | null,
    incoming: DocumentListItem,
    page: number,
): LoadState | null {
    if (current == null || current.status !== "ready") {
        return current;
    }
    const items = current.data.items;
    const index = items.findIndex((item) => item.id === incoming.id);
    if (index >= 0) {
        if (!isDocumentUpdateNewer(incoming, items[index])) {
            return current;
        }
        const next = items.slice();
        next[index] = {...items[index], ...incoming};
        return {
            ...current,
            data: {...current.data, items: next},
        };
    }
    if (page !== 1) {
        return current;
    }
    return {
        ...current,
        data: {
            ...current.data,
            items: [incoming, ...items].slice(0, DOCUMENTS_PER_PAGE),
            total: current.data.total + 1,
        },
    };
}
