import {ArrowUp, Square} from "lucide-react";
import {type FormEvent, type KeyboardEvent, type ReactNode} from "react";

import {useI18n} from "@/shared/i18n/I18nProvider";

type ChatComposerProps = {
    value: string;
    pending: boolean;
    onChange: (value: string) => void;
    onSubmit: () => void;
    onCancel: () => void;
    /** Shown above the input (the document picker). */
    toolbar?: ReactNode;
};

export function ChatComposer({
    value,
    pending,
    onChange,
    onSubmit,
    onCancel,
    toolbar,
}: ChatComposerProps) {
    const {t} = useI18n();
    const canSend = !pending && value.trim().length > 0;

    function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (pending) {
            onCancel();
            return;
        }
        if (!canSend) {
            return;
        }
        onSubmit();
    }

    function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
        if (event.key !== "Enter" || event.shiftKey) {
            return;
        }
        event.preventDefault();
        if (pending || !canSend) {
            return;
        }
        onSubmit();
    }

    return (
        <form
            className="flex shrink-0 flex-col gap-2 border-t border-base-300 p-3"
            aria-label={t("chat.sendForm")}
            onSubmit={handleSubmit}
        >
            {toolbar}
            <div className="flex items-end gap-2">
                <label className="sr-only" htmlFor="chat-message">
                    {t("chat.messageLabel")}
                </label>
                <textarea
                    id="chat-message"
                    name="message"
                    rows={2}
                    value={value}
                    disabled={pending}
                    placeholder={t("chat.placeholder")}
                    className="d-textarea max-h-40 min-h-12 w-full resize-none"
                    onChange={(event) => onChange(event.target.value)}
                    onKeyDown={handleKeyDown}
                />
                {pending ? (
                    <button
                        type="submit"
                        className="d-btn d-btn-primary d-btn-square"
                        aria-label={t("chat.stop")}
                    >
                        <Square className="size-3.5 fill-current" aria-hidden />
                    </button>
                ) : (
                    <button
                        type="submit"
                        className="d-btn d-btn-primary d-btn-square"
                        disabled={!canSend}
                        aria-label={t("chat.send")}
                    >
                        <ArrowUp className="size-4" aria-hidden />
                    </button>
                )}
            </div>
        </form>
    );
}
