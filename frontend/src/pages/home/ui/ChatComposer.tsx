import {ArrowUp, Square} from "lucide-react";
import {type FormEvent, type KeyboardEvent} from "react";

import {Button} from "@/components/ui/button";
import {Textarea} from "@/components/ui/textarea";

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
            aria-label="Send a message"
            onSubmit={handleSubmit}
        >
            <label className="sr-only" htmlFor="chat-message">
                Message
            </label>
            <Textarea
                id="chat-message"
                name="message"
                rows={2}
                value={value}
                disabled={pending}
                placeholder="Ask about your documents"
                className="max-h-40 min-h-12 resize-none"
                onChange={(event) => onChange(event.target.value)}
                onKeyDown={handleKeyDown}
            />
            {pending ? (
                <Button
                    type="submit"
                    size="icon"
                    aria-label="Stop generating"
                >
                    <Square className="size-3.5 fill-current" />
                </Button>
            ) : (
                <Button
                    type="submit"
                    size="icon"
                    disabled={!canSend}
                    aria-label="Send"
                >
                    <ArrowUp />
                </Button>
            )}
        </form>
    );
}
