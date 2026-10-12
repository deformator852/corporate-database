import {useI18n} from "@/shared/i18n/I18nProvider";
import {ConfirmDialog} from "@/shared/ui/ConfirmDialog";
import {deleteReviewedChat} from "@pages/chat-history/api/chatHistory";

/** Confirms deleting one user's chat (`chat` null: closed). */
export function ChatDeleteDialog({
    chat,
    onClose,
    onDeleted,
}: {
    chat: {id: number; userName: string} | null;
    onClose: () => void;
    onDeleted: () => void;
}) {
    const {t} = useI18n();
    return (
        <ConfirmDialog
            open={chat != null}
            onOpenChange={(open) => {
                if (!open) {
                    onClose();
                }
            }}
            title={t("chatHistory.delete.title")}
            description={t("chatHistory.delete.description", {name: chat?.userName ?? ""})}
            confirmLabel={t("common.delete")}
            pendingLabel={t("common.deleting")}
            errorMessage={t("chatHistory.delete.error")}
            onConfirm={async () => {
                if (chat) {
                    await deleteReviewedChat(chat.id);
                    onDeleted();
                }
            }}
        />
    );
}
