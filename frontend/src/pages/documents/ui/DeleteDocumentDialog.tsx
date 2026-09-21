import {useState} from "react";
import {CircleAlert} from "lucide-react";

import {
    AlertDialog,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {Button} from "@/components/ui/button";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {deleteDocument} from "@pages/documents/api/documents";
import type {DocumentListItem} from "@pages/documents/model/documents";

type DeleteDocumentDialogProps = {
    document: DocumentListItem | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onDeleted: () => void;
};

export function DeleteDocumentDialog({
    document,
    open,
    onOpenChange,
    onDeleted,
}: DeleteDocumentDialogProps) {
    const [pending, setPending] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const name = document?.name ?? "this document";

    const handleOpenChange = (next: boolean) => {
        if (pending) {
            return;
        }
        if (!next) {
            setError(null);
        }
        onOpenChange(next);
    };

    const handleDelete = async () => {
        if (document == null) {
            return;
        }
        setPending(true);
        setError(null);
        try {
            await deleteDocument(document.id);
            onDeleted();
            onOpenChange(false);
        } catch (reason) {
            setError(getApiErrorMessage(reason, "Could not delete the document."));
        } finally {
            setPending(false);
        }
    };

    return (
        <AlertDialog open={open} onOpenChange={handleOpenChange}>
            <AlertDialogContent>
                <AlertDialogHeader>
                    <AlertDialogTitle>Delete {name}?</AlertDialogTitle>
                    <AlertDialogDescription>
                        The file and its search data will be removed. This cannot be undone.
                    </AlertDialogDescription>
                </AlertDialogHeader>
                {error ? (
                    <div
                        role="alert"
                        className="flex gap-2.5 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2.5 text-sm text-destructive"
                    >
                        <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
                        <p>{error}</p>
                    </div>
                ) : null}
                <AlertDialogFooter>
                    <AlertDialogCancel disabled={pending}>Cancel</AlertDialogCancel>
                    <Button
                        type="button"
                        variant="destructive"
                        disabled={pending || document == null}
                        onClick={() => {
                            void handleDelete();
                        }}
                    >
                        {pending ? "Deleting…" : "Delete"}
                    </Button>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    );
}
