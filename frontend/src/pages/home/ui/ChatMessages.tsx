import {useEffect, useRef} from "react";

import type {ChatMessage, ChatStatus} from "@pages/home/model/chat";

type ChatMessagesProps = {
    messages: ChatMessage[];
    status: ChatStatus;
    error: string | null;
    onRetry: () => void;
};

function bubbleClass(role: ChatMessage["role"]) {
    if (role === "user") {
        return "ml-auto bg-primary text-primary-foreground";
    }
    return "mr-auto bg-muted text-foreground";
}

export function ChatMessages({messages, status, error, onRetry}: ChatMessagesProps) {
    const scrollerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const scroller = scrollerRef.current;
        if (!scroller) {
            return;
        }
        scroller.scrollTop = scroller.scrollHeight;
    }, [messages, status, error]);

    if (messages.length === 0 && status === "idle") {
        return (
            <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 px-6 py-10 text-center">
                <p className="text-base font-medium">Ask the assistant</p>
                <p className="max-w-sm text-sm text-muted-foreground">
                    Questions about this workspace go here. Send a message to start.
                </p>
            </div>
        );
    }

    return (
        <div
            ref={scrollerRef}
            role="log"
            aria-live="polite"
            aria-relevant="additions"
            aria-label="Conversation"
            className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto overscroll-contain px-4 py-4"
        >
            {messages.map((message) => (
                <p
                    key={message.id}
                    className={`max-w-[min(100%,36rem)] rounded-2xl px-3.5 py-2.5 text-sm break-words whitespace-pre-wrap ${bubbleClass(message.role)}`}
                >
                    <span className="sr-only">
                        {message.role === "user" ? "You: " : "Assistant: "}
                    </span>
                    {message.content}
                </p>
            ))}

            {status === "pending" ? (
                <p
                    className="mr-auto flex max-w-[min(100%,36rem)] items-center gap-1 rounded-2xl bg-muted px-3.5 py-2.5 text-sm text-muted-foreground"
                    aria-label="Assistant is writing"
                >
                    <span className="size-1.5 animate-pulse rounded-full bg-muted-foreground" />
                    <span className="size-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:150ms]" />
                    <span className="size-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:300ms]" />
                </p>
            ) : null}

            {status === "error" && error ? (
                <div className="mr-auto max-w-[min(100%,36rem)] space-y-2 rounded-2xl bg-destructive/10 px-3.5 py-2.5 text-sm text-destructive">
                    <p>{error}</p>
                    <button
                        type="button"
                        className="cursor-pointer font-medium underline-offset-2 hover:underline"
                        onClick={onRetry}
                    >
                        Try again
                    </button>
                </div>
            ) : null}
        </div>
    );
}
