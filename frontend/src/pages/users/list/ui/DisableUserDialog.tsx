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
import {useI18n} from "@/shared/i18n/I18nProvider";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {disableUser} from "@pages/users/list/api/users";
import type {UserListItem} from "@pages/users/list/model/users";

type DisableUserDialogProps = {
    user: UserListItem | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onDisabled: () => void;
};

/** Offboarding: blocks sign-in, keeps the account and its history. */
export function DisableUserDialog({
    user,
    open,
    onOpenChange,
    onDisabled,
}: DisableUserDialogProps) {
    const {t} = useI18n();
    const [pending, setPending] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const name = user
        ? `${user.first_name} ${user.last_name}`
        : t("common.thisUser");

    const handleOpenChange = (next: boolean) => {
        if (pending) {
            return;
        }
        if (!next) {
            setError(null);
        }
        onOpenChange(next);
    };

    const handleDisable = async () => {
        if (user == null) {
            return;
        }
        setPending(true);
        setError(null);
        try {
            await disableUser(user.id);
            onDisabled();
            onOpenChange(false);
        } catch (reason) {
            setError(getApiErrorMessage(reason, t("users.disableDialog.error")));
        } finally {
            setPending(false);
        }
    };

    return (
        <AlertDialog open={open} onOpenChange={handleOpenChange}>
            <AlertDialogContent>
                <AlertDialogHeader>
                    <AlertDialogTitle>
                        {t("users.disableDialog.title", {name})}
                    </AlertDialogTitle>
                    <AlertDialogDescription>
                        {t("users.disableDialog.description")}
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
                    <AlertDialogCancel disabled={pending}>
                        {t("common.cancel")}
                    </AlertDialogCancel>
                    <Button
                        type="button"
                        variant="destructive"
                        disabled={pending || user == null}
                        onClick={() => {
                            void handleDisable();
                        }}
                    >
                        {pending ? t("common.disabling") : t("users.disableDialog.confirm")}
                    </Button>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    );
}
