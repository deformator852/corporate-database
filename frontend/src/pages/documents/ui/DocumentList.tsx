import {CircleAlert, FileText, Pencil, RotateCw} from "lucide-react";
import {useState} from "react";

import {Button} from "@/components/ui/button";
import {TableCell, TableRow} from "@/components/ui/table";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {ListPagination} from "@/shared/ui/ListPagination";
import {DataTable} from "@/shared/ui/DataTable";
import {DeleteButton} from "@/shared/ui/DeleteButton";
import {StatusCard} from "@/shared/ui/StatusCard";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {openDocumentFile} from "@/shared/lib/documentFile";
import {documentClassificationKey, documentStatusKey} from "@/entities/document/model";
import {
    type DocumentListItem,
    type DocumentListPage,
} from "@pages/documents/model/documents";
import {type DocumentStatus} from "@/entities/document/model";

type DocumentListProps = {
    headingId: string;
    status: "loading" | "ready" | "error";
    error: string | null;
    data: DocumentListPage | null;
    page: number;
    /** Row actions the user may take; the column shows if any. */
    actions?: DocumentActions;
    onRetry: () => void;
    onPageChange: (page: number) => void;
    /** Empty because of the filters, not because there are no documents. */
    filtered?: boolean;
    onClearFilters?: () => void;
};

type DocumentActions = {
    onEdit?: (document: DocumentListItem) => void;
    /** Processes a failed document again; rejects with the server's reason. */
    onProcessAgain?: (document: DocumentListItem) => Promise<void>;
    onDelete?: (document: DocumentListItem) => void;
};

export function DocumentList({
    headingId,
    status,
    error,
    data,
    page,
    actions = {},
    onRetry,
    onPageChange,
    filtered = false,
    onClearFilters,
}: DocumentListProps) {
    const {t} = useI18n();
    const items = data?.items ?? [];
    const total = data?.total ?? 0;
    const pages = data?.pages ?? 0;
    const hasActions = Boolean(actions.onEdit || actions.onProcessAgain || actions.onDelete);

    if (status === "error") {
        return (
            <StatusCard title={t("documents.loadErrorTitle")} detail={error} onRetry={onRetry} />
        );
    }

    if (status === "ready" && total === 0) {
        return (
            filtered ? (
                <StatusCard title={t("documents.filter.noMatch")}>
                    <Button type="button" variant="outline" onClick={onClearFilters}>
                        {t("documents.filter.clear")}
                    </Button>
                </StatusCard>
            ) : (
                <StatusCard title={t("documents.emptyTitle")} detail={t("documents.emptyDescription")} />
            )
        );
    }

    return (
        <div className="stack">
            <DataTable
                aria-labelledby={headingId}
                columns={[
                    {label: t("common.name"), className: "px-4"},
                    {label: t("common.file")},
                    {label: t("common.access")},
                    {label: t("common.status")},
                    {label: t("common.progress"), className: "px-4"},
                    hasActions && {label: <span className="sr-only">{t("common.actions")}</span>, className: "px-4"},
                ]}
                loading={status === "loading"}
                loadingText={t("documents.loading")}
            >
                {items.map((document) => (
                    <DocumentRow key={document.id} document={document} actions={hasActions ? actions : null} />
                ))}
            </DataTable>
            {data && pages > 1 ? (
                <ListPagination
                    page={page}
                    pages={pages}
                    perPage={data.per_page}
                    total={total}
                    shown={items.length}
                    onPageChange={onPageChange}
                />
            ) : null}
        </div>
    );
}

function DocumentRow({
    document,
    actions,
}: {
    document: DocumentListItem;
    /** null: no actions column. */
    actions: DocumentActions | null;
}) {
    const {t} = useI18n();
    const status = document.status as DocumentStatus;
    const [openError, setOpenError] = useState<string | null>(null);
    const [retrying, setRetrying] = useState(false);
    const [retryError, setRetryError] = useState<string | null>(null);
    const failed = document.status === "failed";
    const processing = !failed && document.status !== "completed";

    async function processAgain() {
        if (!actions?.onProcessAgain) {
            return;
        }
        setRetrying(true);
        setRetryError(null);
        try {
            await actions.onProcessAgain(document);
        } catch (reason) {
            setRetryError(getApiErrorMessage(reason, t("documents.retry.error")));
        } finally {
            setRetrying(false);
        }
    }
    return (
        <TableRow>
            <TableCell className="px-4 font-medium">
                <button
                    type="button"
                    className="inline-flex cursor-pointer items-center gap-1.5 rounded-sm text-left underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
                    title={t("documents.open")}
                    onClick={() => {
                        setOpenError(null);
                        void openDocumentFile(document.id, document.filename).catch((reason) =>
                            setOpenError(getApiErrorMessage(reason, t("documents.openError"))),
                        );
                    }}
                >
                    <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                    {document.name}
                </button>
                {openError ? (
                    <p role="alert" className="mt-1 text-xs font-normal text-destructive">
                        {openError}
                    </p>
                ) : null}
            </TableCell>
            <TableCell className="text-muted-foreground">{document.filename}</TableCell>
            <TableCell>
                {t(documentClassificationKey(document.classification))}
            </TableCell>
            <TableCell>
                <div className="flex flex-col gap-1">
                    <span>{t(documentStatusKey(status))}</span>
                    {document.status === "failed" && document.error_message ? (
                        <p className="flex items-start gap-1 text-sm text-destructive">
                            <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                            {document.error_message}
                        </p>
                    ) : null}
                </div>
            </TableCell>
            <TableCell className="px-4">
                <div className="flex items-center gap-2">
                    <div
                        className="h-1.5 w-24 overflow-hidden rounded-full bg-muted"
                        role="progressbar"
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={document.progress}
                        aria-label={`${document.progress}%`}
                    >
                        <div
                            className="h-full bg-primary"
                            style={{width: `${document.progress}%`}}
                        />
                    </div>
                    <span className="text-sm text-muted-foreground tabular-nums">
                        {document.progress}%
                    </span>
                </div>
            </TableCell>
            {actions ? (
                <TableCell className="px-4">
                    <div className="flex flex-wrap justify-end gap-1.5">
                        {failed && actions.onProcessAgain ? (
                            <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                disabled={retrying}
                                aria-label={t("documents.retry.label", {name: document.name})}
                                onClick={() => void processAgain()}
                            >
                                <RotateCw aria-hidden className={retrying ? "animate-spin" : undefined} />
                                {t("documents.retry.button")}
                            </Button>
                        ) : null}
                        {actions.onEdit ? (
                            <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                // While processing, the worker writes the values it started with.
                                disabled={processing}
                                title={processing ? t("documents.edit.waitProcessing") : undefined}
                                aria-label={t("documents.edit.label", {name: document.name})}
                                onClick={() => actions.onEdit?.(document)}
                            >
                                <Pencil aria-hidden />
                                {t("common.edit")}
                            </Button>
                        ) : null}
                        {actions.onDelete ? (
                            <DeleteButton
                                aria-label={t("documents.delete.title", {
                                    name: document.name,
                                })}
                                onClick={() => actions.onDelete?.(document)}
                            />
                        ) : null}
                    </div>
                    {retryError ? (
                        <p role="alert" className="mt-1 text-right text-xs text-destructive">
                            {retryError}
                        </p>
                    ) : null}
                </TableCell>
            ) : null}
        </TableRow>
    );
}
