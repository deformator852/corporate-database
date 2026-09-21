import {ArrowUp} from "lucide-react";
import {type FormEvent, type KeyboardEvent} from "react";

import {Button} from "@/components/ui/button";
import {Textarea} from "@/components/ui/textarea";

type ChatComposerProps = {
    value: string;
    disabled: boolean;
    onChange: (value: string) => void;
    onSubmit: () => void;
};

export function ChatComposer({value, disabled, onChange, onSubmit}: ChatComposerProps) {
    const canSend = !disabled && value.trim().length > 0;

    function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
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
        if (!canSend) {
            return;
        }
        onSubmit();
    }

    return (
        <form
            className="flex items-end gap-2 border-t border-border p-3"
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
                disabled={disabled}
                placeholder="Message"
                className="max-h-40 min-h-12 resize-none"
                onChange={(event) => onChange(event.target.value)}
                onKeyDown={handleKeyDown}
            />
            <Button
                type="submit"
                size="icon"
                disabled={!canSend}
                aria-label="Send"
            >
                <ArrowUp />
            </Button>
        </form>
    );
}
