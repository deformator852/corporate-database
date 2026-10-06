import {CircleAlert, FileText, Trash2} from "lucide-react";
import {useState} from "react";

import {Button} from "@/components/ui/button";
import {Card} from "@/components/ui/card";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {ListPagination} from "@/shared/ui/ListPagination";
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
    canDelete?: boolean;
    onRetry: () => void;
    onPageChange: (page: number) => void;
    onDelete?: (document: DocumentListItem) => void;
};

export function DocumentList({
    headingId,
    status,
    error,
    data,
    page,
    canDelete = false,
    onRetry,
    onPageChange,
    onDelete,
}: DocumentListProps) {
    const {t} = useI18n();
    const items = data?.items ?? [];
    const total = data?.total ?? 0;
    const pages = data?.pages ?? 0;
    const columns = canDelete ? 6 : 5;

    if (status === "error") {
        return (
            <StatusCard title={t("documents.loadErrorTitle")} detail={error} onRetry={onRetry} />
        );
    }

    if (status === "ready" && total === 0) {
        return (
            <StatusCard title={t("documents.emptyTitle")} detail={t("documents.emptyDescription")} />
        );
    }

    return (
        <div className="stack">
            <Card className="gap-0 py-0">
                <Table aria-labelledby={headingId}>
                    <TableHeader>
                        <TableRow className="hover:bg-transparent">
                            <TableHead className="px-4">{t("common.name")}</TableHead>
                            <TableHead>{t("common.file")}</TableHead>
                            <TableHead>{t("common.access")}</TableHead>
                            <TableHead>{t("common.status")}</TableHead>
                            <TableHead className="px-4">{t("common.progress")}</TableHead>
                            {canDelete ? (
                                <TableHead className="px-4">
                                    <span className="sr-only">{t("common.actions")}</span>
                                </TableHead>
                            ) : null}
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {status === "loading" ? (
                            <TableRow className="hover:bg-transparent">
                                <TableCell
                                    colSpan={columns}
                                    className="px-4 py-8 text-muted-foreground"
                                >
                                    {t("documents.loading")}
                                </TableCell>
                            </TableRow>
                        ) : (
                            items.map((document) => (
                                <DocumentRow
                                    key={document.id}
                                    document={document}
                                    canDelete={canDelete}
                                    onDelete={onDelete}
                                />
                            ))
                        )}
                    </TableBody>
                </Table>
            </Card>
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
    canDelete,
    onDelete,
}: {
    document: DocumentListItem;
    canDelete: boolean;
    onDelete?: (document: DocumentListItem) => void;
}) {
    const {t} = useI18n();
    const status = document.status as DocumentStatus;
    const [openError, setOpenError] = useState<string | null>(null);
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
            {canDelete ? (
                <TableCell className="px-4">
                    <div className="flex justify-end">
                        <Button
                            type="button"
                            variant="destructive"
                            size="sm"
                            aria-label={t("documents.delete.title", {
                                name: document.name,
                            })}
                            onClick={() => onDelete?.(document)}
                        >
                            <Trash2 aria-hidden />
                            {t("common.delete")}
                        </Button>
                    </div>
                </TableCell>
            ) : null}
        </TableRow>
    );
}
