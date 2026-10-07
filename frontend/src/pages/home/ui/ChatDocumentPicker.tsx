import {Files, X} from "lucide-react";
import {useRef, useState} from "react";

import {Button} from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {SearchablePicker} from "@/shared/ui/SearchablePicker";
import {getReadyDocumentsPage} from "@pages/home/api/documents";
import {MAX_CHAT_DOCUMENTS, type ChatDocument} from "@pages/home/model/chat";

type ChatDocumentPickerProps = {
    value: ChatDocument[];
    onChange: (documents: ChatDocument[]) => void;
    disabled: boolean;
};

/** Limits the chat to chosen documents; none chosen searches all. */
export function ChatDocumentPicker({value, onChange, disabled}: ChatDocumentPickerProps) {
    const {t} = useI18n();
    const [open, setOpen] = useState(false);
    // Names of documents the picker has shown: it reports ids only.
    const names = useRef(new Map<string, string>());

    const loadPage = async (page: number, perPage: number, query: string) => {
        const result = await getReadyDocumentsPage(page, perPage, query);
        for (const item of result.items) {
            names.current.set(item.key, item.name);
        }
        return result;
    };

    const choose = (keys: string[]) => {
        if (keys.length > MAX_CHAT_DOCUMENTS) {
            return;
        }
        const known = new Map(value.map((document) => [String(document.id), document.name]));
        onChange(keys.map((key) => ({id: Number(key), name: names.current.get(key) ?? known.get(key) ?? key})));
    };

    return (
        <div className="flex flex-wrap items-center gap-1.5">
            <Button
                type="button"
                variant="ghost"
                size="sm"
                className="text-muted-foreground"
                disabled={disabled}
                onClick={() => setOpen(true)}
            >
                <Files aria-hidden />
                {value.length ? t("chat.documents.chosen", {count: value.length}) : t("chat.documents.all")}
            </Button>
            {value.map((document) => (
                <span
                    key={document.id}
                    className="inline-flex max-w-56 items-center gap-0.5 rounded-full bg-muted py-0.5 ps-2.5 pe-0.5 text-xs"
                >
                    <span className="truncate">{document.name}</span>
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon-xs"
                        className="rounded-full"
                        disabled={disabled}
                        aria-label={t("chat.documents.remove", {name: document.name})}
                        onClick={() => onChange(value.filter((item) => item.id !== document.id))}
                    >
                        <X aria-hidden />
                    </Button>
                </span>
            ))}

            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="sm:max-w-md" showCloseButton>
                    <DialogHeader>
                        <DialogTitle>{t("chat.documents.title")}</DialogTitle>
                        <DialogDescription>
                            {t("chat.documents.description", {count: MAX_CHAT_DOCUMENTS})}
                        </DialogDescription>
                    </DialogHeader>
                    <SearchablePicker
                        value={value.map((document) => String(document.id))}
                        onChange={choose}
                        enabled={open}
                        idPrefix="chat-document"
                        loadPage={loadPage}
                        labels={{
                            search: t("chat.documents.search"),
                            loading: t("documents.loading"),
                            loadError: t("documents.loadError"),
                            empty: t("chat.documents.empty"),
                            emptySearch: t("chat.documents.emptySearch"),
                        }}
                    />
                    <DialogFooter>
                        <Button type="button" variant="outline" disabled={!value.length} onClick={() => onChange([])}>
                            {t("chat.documents.clear")}
                        </Button>
                        <Button type="button" onClick={() => setOpen(false)}>
                            {t("chat.documents.done")}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
