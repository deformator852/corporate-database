import {ArrowUp, Square} from "lucide-react";
import {type FormEvent, type KeyboardEvent} from "react";

import {Button} from "@/components/ui/button";
import {Textarea} from "@/components/ui/textarea";
import {useI18n} from "@/shared/i18n/I18nProvider";

type ChatComposerProps = {
    value: string;
    pending: boolean;
    onChange: (value: string) => void;
    onSubmit: () => void;
    onCancel: () => void;
};

export function ChatComposer({
    value,
    pending,
    onChange,
    onSubmit,
    onCancel,
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
            className="flex shrink-0 items-end gap-2 border-t border-border p-3"
            aria-label={t("chat.sendForm")}
            onSubmit={handleSubmit}
        >
            <label className="sr-only" htmlFor="chat-message">
                {t("chat.messageLabel")}
            </label>
            <Textarea
                id="chat-message"
                name="message"
                rows={2}
                value={value}
                disabled={pending}
                placeholder={t("chat.placeholder")}
                className="max-h-40 min-h-12 resize-none"
                onChange={(event) => onChange(event.target.value)}
                onKeyDown={handleKeyDown}
            />
            {pending ? (
                <Button
                    type="submit"
                    size="icon"
                    aria-label={t("chat.stop")}
                >
                    <Square className="size-3.5 fill-current" />
                </Button>
            ) : (
                <Button
                    type="submit"
                    size="icon"
                    disabled={!canSend}
                    aria-label={t("chat.send")}
                >
                    <ArrowUp />
                </Button>
            )}
        </form>
    );
}
