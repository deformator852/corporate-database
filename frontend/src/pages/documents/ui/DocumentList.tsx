import {CircleAlert, Trash2} from "lucide-react";

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
import {
    DOCUMENT_CLASSIFICATION_LABELS,
    DOCUMENT_STATUS_LABELS,
    type DocumentListItem,
    type DocumentListPage,
    type DocumentStatus,
} from "@pages/documents/model/documents";

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
    const items = data?.items ?? [];
    const total = data?.total ?? 0;
    const pages = data?.pages ?? 0;
    const perPage = data?.per_page ?? 20;
    const from = total === 0 ? 0 : (page - 1) * perPage + 1;
    const to = total === 0 ? 0 : (page - 1) * perPage + items.length;
    const columns = canDelete ? 6 : 5;

    if (status === "error") {
        return (
            <div className="flex flex-col items-start gap-3 rounded-xl bg-card px-4 py-8 ring-1 ring-foreground/10">
                <p className="font-medium">Could not load documents</p>
                <p className="text-sm text-muted-foreground">{error}</p>
                <Button type="button" onClick={onRetry}>
                    Try again
                </Button>
            </div>
        );
    }

    if (status === "ready" && total === 0) {
        return (
            <div className="flex flex-col items-start gap-3 rounded-xl bg-card px-4 py-8 ring-1 ring-foreground/10">
                <p className="font-medium">No documents yet</p>
                <p className="text-sm text-muted-foreground">
                    Upload a file to start processing.
                </p>
            </div>
        );
    }

    return (
        <div className="stack">
            <Card className="gap-0 py-0">
                <Table aria-labelledby={headingId}>
                    <TableHeader>
                        <TableRow className="hover:bg-transparent">
                            <TableHead className="px-4">Name</TableHead>
                            <TableHead>File</TableHead>
                            <TableHead>Access</TableHead>
                            <TableHead>Status</TableHead>
                            <TableHead className="px-4">Progress</TableHead>
                            {canDelete ? (
                                <TableHead className="px-4">
                                    <span className="sr-only">Actions</span>
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
                                    Loading documents…
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
            {status === "ready" && pages > 1 ? (
                <div className="flex flex-wrap items-center justify-between gap-3">
                    <p className="text-sm text-muted-foreground">
                        {from}–{to} of {total}
                    </p>
                    <div className="flex gap-2">
                        <Button
                            type="button"
                            variant="outline"
                            disabled={page <= 1}
                            onClick={() => onPageChange(page - 1)}
                        >
                            Previous
                        </Button>
                        <Button
                            type="button"
                            variant="outline"
                            disabled={page >= pages}
                            onClick={() => onPageChange(page + 1)}
                        >
                            Next
                        </Button>
                    </div>
                </div>
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
    const status = document.status as DocumentStatus;
    return (
        <TableRow>
            <TableCell className="px-4 font-medium">{document.name}</TableCell>
            <TableCell className="text-muted-foreground">{document.filename}</TableCell>
            <TableCell>
                {DOCUMENT_CLASSIFICATION_LABELS[document.classification] ??
                    document.classification}
            </TableCell>
            <TableCell>
                <div className="flex flex-col gap-1">
                    <span>{DOCUMENT_STATUS_LABELS[status] ?? document.status}</span>
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
                        aria-label={`${document.progress} percent`}
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
                            aria-label={`Delete ${document.name}`}
                            onClick={() => onDelete?.(document)}
                        >
                            <Trash2 aria-hidden />
                            Delete
                        </Button>
                    </div>
                </TableCell>
            ) : null}
        </TableRow>
    );
}
