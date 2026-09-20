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
import {deleteRole} from "@pages/roles/list/api/roles";
import type {RoleListItem} from "@pages/roles/list/model/roles";

type DeleteRoleDialogProps = {
    role: RoleListItem | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onDeleted: () => void;
};

export function DeleteRoleDialog({
    role,
    open,
    onOpenChange,
    onDeleted,
}: DeleteRoleDialogProps) {
    const [pending, setPending] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const name = role?.name ?? "this role";

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
        if (role == null) {
            return;
        }
        setPending(true);
        setError(null);
        try {
            await deleteRole(role.key);
            onDeleted();
            onOpenChange(false);
        } catch (reason) {
            setError(getApiErrorMessage(reason, "Could not delete role."));
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
                        Users with this role will lose its permissions. This cannot be undone.
                    </AlertDialogDescription>
                </AlertDialogHeader>
                {error ? (
                    <div
                        role="alert"
                        className="flex gap-2.5 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2.5 text-sm text-destructive"
                    >
                        <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden/>
                        <p>{error}</p>
                    </div>
                ) : null}
                <AlertDialogFooter>
                    <AlertDialogCancel disabled={pending}>Cancel</AlertDialogCancel>
                    <Button
                        type="button"
                        variant="destructive"
                        disabled={pending || role == null}
                        onClick={() => {
                            void handleDelete();
                        }}
                    >
                        {pending ? "Deleting…" : "Delete role"}
                    </Button>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    );
}
