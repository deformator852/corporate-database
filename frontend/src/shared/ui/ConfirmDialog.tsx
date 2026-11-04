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

type ConfirmDialogProps = {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    title: string;
    description: string;
    confirmLabel: string;
    pendingLabel: string;
    /** Shown when the server gives no message of its own. */
    errorMessage: string;
    /** The action; the dialog closes when it resolves and shows the error when it throws. */
    onConfirm: () => Promise<void>;
};

/** Confirmation for a destructive action (delete, disable). */
export function ConfirmDialog({
    open,
    onOpenChange,
    title,
    description,
    confirmLabel,
    pendingLabel,
    errorMessage,
    onConfirm,
}: ConfirmDialogProps) {
    const {t} = useI18n();
    const [pending, setPending] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleOpenChange = (next: boolean) => {
        if (pending) {
            return;
        }
        if (!next) {
            setError(null);
        }
        onOpenChange(next);
    };

    const handleConfirm = async () => {
        setPending(true);
        setError(null);
        try {
            await onConfirm();
            onOpenChange(false);
        } catch (reason) {
            setError(getApiErrorMessage(reason, errorMessage));
        } finally {
            setPending(false);
        }
    };

    return (
        <AlertDialog open={open} onOpenChange={handleOpenChange}>
            <AlertDialogContent>
                <AlertDialogHeader>
                    <AlertDialogTitle>{title}</AlertDialogTitle>
                    <AlertDialogDescription>{description}</AlertDialogDescription>
                </AlertDialogHeader>
                {error ? (
                    <div
                        role="alert"
                        className="d-alert d-alert-error d-alert-soft items-start text-sm"
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
                        disabled={pending}
                        onClick={() => {
                            void handleConfirm();
                        }}
                    >
                        {pending ? pendingLabel : confirmLabel}
                    </Button>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    );
}
