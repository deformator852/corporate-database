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
            className="shrink-0 border-t border-base-300 p-3 md:px-6"
            aria-label={t("chat.sendForm")}
            onSubmit={handleSubmit}
        >
            <div className="flex max-w-[calc(48rem+2.75rem)] flex-wrap items-end gap-1 rounded-box border border-base-300 focus-within:border-primary focus-within:ring-1 focus-within:ring-primary p-1">
                {/* On its own row on phones: the input needs the width. */}
                {toolbar ? <div className="max-w-full basis-full md:basis-auto">{toolbar}</div> : null}
                <label className="sr-only" htmlFor="chat-message">
                    {t("chat.messageLabel")}
                </label>
                <textarea
                    id="chat-message"
                    name="message"
                    rows={1}
                    value={value}
                    disabled={pending}
                    placeholder={t("chat.placeholder")}
                    className="max-h-40 min-h-8 min-w-40 flex-1 resize-none bg-transparent px-2 py-1 text-sm leading-6 outline-none [field-sizing:content] placeholder:text-base-content/70 disabled:opacity-60"
                    onChange={(event) => onChange(event.target.value)}
                    onKeyDown={handleKeyDown}
                />
                {pending ? (
                    <button type="submit" className="d-btn d-btn-primary d-btn-square d-btn-sm shrink-0" aria-label={t("chat.stop")}>
                        <Square className="size-3 fill-current" aria-hidden />
                    </button>
                ) : (
                    <button type="submit" className="d-btn d-btn-primary d-btn-square d-btn-sm shrink-0" disabled={!canSend} aria-label={t("chat.send")}>
                        <ArrowUp className="size-4" aria-hidden />
                    </button>
                )}
            </div>
        </form>
    );
}
