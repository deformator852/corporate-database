import {Check, Copy, RefreshCw, ThumbsDown, ThumbsUp} from "lucide-react";
import {useEffect, useRef, useState} from "react";

import {Button} from "@/components/ui/button";
import {SourceList} from "@/entities/chat/SourceList";
import type {ChatMessage, ChatStatus} from "@pages/home/model/chat";
import type {AnswerRating} from "@/entities/chat/model";
import {cn} from "cn";
import {useI18n} from "@/shared/i18n/I18nProvider";

type ChatMessagesProps = {
    messages: ChatMessage[];
    /** Partial answer while it is generated; null before the first piece. */
    streaming: string | null;
    status: ChatStatus;
    error: string | null;
    onRetry: () => void;
    onRate?: (message: ChatMessage, rating: AnswerRating | null) => void;
    /** Asks the last question again; offered on the last answer. */
    onRegenerate?: () => void;
};

function bubbleClass(role: ChatMessage["role"]) {
    if (role === "user") {
        return "ml-auto max-w-[min(100%,36rem)] bg-primary text-primary-foreground";
    }
    return "mr-auto w-full max-w-[min(100%,48rem)] bg-muted text-foreground";
}

export function ChatMessages({
    messages,
    streaming,
    status,
    error,
    onRetry,
    onRate,
    onRegenerate,
}: ChatMessagesProps) {
    const {t} = useI18n();
    const scrollerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const scroller = scrollerRef.current;
        if (!scroller) {
            return;
        }
        scroller.scrollTop = scroller.scrollHeight;
    }, [messages, streaming, status, error]);

    if (messages.length === 0 && status === "idle") {
        return (
            <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 px-6 py-10 text-center">
                <p className="text-base font-medium">{t("chat.emptyTitle")}</p>
                <p className="max-w-sm text-sm text-muted-foreground">
                    {t("chat.emptyDescription")}
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
            aria-label={t("chat.conversation")}
            className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain px-4 py-4"
        >
            {messages.map((message, index) => (
                <div key={message.id} className="space-y-1.5">
                    <p
                        className={`rounded-2xl px-3.5 py-2.5 text-sm break-words whitespace-pre-wrap ${bubbleClass(message.role)}`}
                    >
                        <span className="sr-only">
                            {message.role === "user" ? t("chat.you") : t("chat.assistant")}
                        </span>
                        {message.content}
                    </p>
                    {message.role === "assistant" && message.sources?.length ? (
                        <SourceList sources={message.sources} answer={message.content} />
                    ) : null}
                    {message.role === "assistant" ? (
                        <div className="flex items-center gap-0.5">
                            <CopyAnswer text={message.content} />
                            {/* Saved answers only: the server replaces it by id. */}
                            {index === messages.length - 1 &&
                            message.messageId != null &&
                            status !== "pending" &&
                            onRegenerate ? (
                                <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon-xs"
                                    className="text-muted-foreground"
                                    aria-label={t("chat.regenerate")}
                                    title={t("chat.regenerate")}
                                    onClick={onRegenerate}
                                >
                                    <RefreshCw aria-hidden />
                                </Button>
                            ) : null}
                            {message.messageId != null && onRate ? (
                                <RateAnswer
                                    rating={message.rating ?? null}
                                    onRate={(rating) => onRate(message, rating)}
                                />
                            ) : null}
                        </div>
                    ) : null}
                </div>
            ))}

            {status === "pending" && streaming ? (
                // Hidden from the live region: screen readers get the finished
                // answer once, not every piece.
                <p
                    aria-hidden
                    className={`rounded-2xl px-3.5 py-2.5 text-sm break-words whitespace-pre-wrap ${bubbleClass("assistant")}`}
                >
                    {streaming}
                    <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-muted-foreground align-middle" />
                </p>
            ) : null}
            {status === "pending" && streaming ? (
                <span className="sr-only">{t("chat.writing")}</span>
            ) : null}

            {status === "pending" && !streaming ? (
                <p
                    className="mr-auto flex max-w-[min(100%,36rem)] items-center gap-1 rounded-2xl bg-muted px-3.5 py-2.5 text-sm text-muted-foreground"
                    aria-label={t("chat.writing")}
                >
                    <span className="size-1.5 animate-pulse rounded-full bg-muted-foreground" />
                    <span className="size-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:150ms]" />
                    <span className="size-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:300ms]" />
                </p>
            ) : null}

            {status === "refused" && error ? (
                <p
                    role="status"
                    className="mr-auto max-w-[min(100%,36rem)] rounded-2xl bg-muted px-3.5 py-2.5 text-sm text-muted-foreground"
                >
                    {error}
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
                        {t("chat.retry")}
                    </button>
                </div>
            ) : null}
        </div>
    );
}

function CopyAnswer({text}: {text: string}) {
    const {t} = useI18n();
    const [copied, setCopied] = useState<"idle" | "copied" | "failed">("idle");
    const label = copied === "copied" ? t("chat.copied") : copied === "failed" ? t("chat.copyError") : t("chat.copy");

    async function copy() {
        try {
            await navigator.clipboard.writeText(text);
            setCopied("copied");
        } catch {
            // Clipboard blocked (permissions, insecure page): say so.
            setCopied("failed");
        }
        window.setTimeout(() => setCopied("idle"), 2000);
    }

    return (
        <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            className="text-muted-foreground"
            aria-label={label}
            title={label}
            onClick={() => void copy()}
        >
            {copied === "copied" ? <Check aria-hidden /> : <Copy aria-hidden />}
        </Button>
    );
}

/** Good / bad buttons; pressing the chosen one again takes the rating back. */
function RateAnswer({rating, onRate}: {rating: AnswerRating | null; onRate: (rating: AnswerRating | null) => void}) {
    const {t} = useI18n();
    const options = [
        {value: "up", label: t("chat.rating.good"), Icon: ThumbsUp},
        {value: "down", label: t("chat.rating.bad"), Icon: ThumbsDown},
    ] as const;
    return (
        // The title tells, before the click, who sees a rated answer.
        <div className="flex items-center gap-0.5" title={t("chat.rating.hint")}>
            {options.map(({value, label, Icon}) => (
                <Button
                    key={value}
                    type="button"
                    variant="ghost"
                    size="icon-xs"
                    aria-label={label}
                    aria-pressed={rating === value}
                    className={cn("text-muted-foreground", rating === value && "text-foreground")}
                    onClick={() => onRate(rating === value ? null : value)}
                >
                    <Icon className={cn(rating === value && "fill-current")} aria-hidden />
                </Button>
            ))}
            <span className="sr-only">{t("chat.rating.hint")}</span>
        </div>
    );
}
