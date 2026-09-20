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
import {deleteUser} from "@pages/users/list/api/users";
import type {UserListItem} from "@pages/users/list/model/users";

type DeleteUserDialogProps = {
    user: UserListItem | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onDeleted: () => void;
};

export function DeleteUserDialog({
    user,
    open,
    onOpenChange,
    onDeleted,
}: DeleteUserDialogProps) {
    const [pending, setPending] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const name = user ? `${user.first_name} ${user.last_name}` : "this user";

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
        if (user == null) {
            return;
        }
        setPending(true);
        setError(null);
        try {
            await deleteUser(user.id);
            onDeleted();
            onOpenChange(false);
        } catch (reason) {
            setError(getApiErrorMessage(reason, "Could not delete user."));
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
                        This person will lose access immediately. This cannot be undone.
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
                        disabled={pending || user == null}
                        onClick={() => {
                            void handleDelete();
                        }}
                    >
                        {pending ? "Deleting…" : "Delete user"}
                    </Button>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    );
}
