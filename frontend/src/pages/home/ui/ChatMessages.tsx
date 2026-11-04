import {Check, Copy, RefreshCw, ThumbsDown, ThumbsUp} from "lucide-react";
import {useEffect, useRef, useState} from "react";

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

// Within this distance of the bottom, the conversation follows new text.
const FOLLOW_MARGIN_PX = 40;

const ICON_BUTTON = "d-btn d-btn-ghost d-btn-square d-btn-xs text-base-content/70";

function bubbleClass(role: ChatMessage["role"]) {
    if (role === "user") {
        // Selected text inverts the bubble's own colors, or it would not show.
        return "d-chat-bubble d-chat-bubble-primary max-w-[min(100%,36rem)] selection:bg-primary-content selection:text-primary";
    }
    return "d-chat-bubble w-full max-w-[min(100%,48rem)] bg-base-200";
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
    // Follows new text only while the reader is at the bottom: someone who
    // scrolled up to read or select an earlier answer stays where they are.
    const following = useRef(true);

    useEffect(() => {
        const scroller = scrollerRef.current;
        if (scroller && following.current) {
            scroller.scrollTop = scroller.scrollHeight;
        }
    }, [messages, streaming, status, error]);

    const onScroll = () => {
        const scroller = scrollerRef.current;
        if (scroller) {
            following.current = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight <= FOLLOW_MARGIN_PX;
        }
    };

    if (messages.length === 0 && status === "idle") {
        return (
            <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 px-6 py-10 text-center">
                <p className="text-lg font-semibold">{t("chat.emptyTitle")}</p>
                <p className="max-w-sm text-sm text-base-content/70">
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
            onScroll={onScroll}
        >
            {messages.map((message, index) => (
                <div key={message.id} className="space-y-1.5">
                    <div className={message.role === "user" ? "d-chat d-chat-end" : "d-chat d-chat-start"}>
                        <p
                            data-ai-generated={message.role === "assistant" ? "true" : undefined}
                            className={`text-sm break-words whitespace-pre-wrap ${bubbleClass(message.role)}`}
                        >
                            {/* For screen readers; not part of a selection or a copy. */}
                            <span className="sr-only select-none">
                                {message.role === "user" ? t("chat.you") : t("chat.assistant")}
                            </span>
                            {message.content}
                        </p>
                    </div>
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
                                <button
                                    type="button"
                                    className={ICON_BUTTON}
                                    aria-label={t("chat.regenerate")}
                                    title={t("chat.regenerate")}
                                    onClick={onRegenerate}
                                >
                                    <RefreshCw className="size-3.5" aria-hidden />
                                </button>
                            ) : null}
                            {message.messageId != null && onRate ? (
                                <RateAnswer
                                    rating={message.rating ?? null}
                                    onRate={(rating) => onRate(message, rating)}
                                />
                            ) : null}
                            <span className="ml-1 text-xs text-base-content/70">{t("chat.aiGenerated")}</span>
                        </div>
                    ) : null}
                </div>
            ))}

            {status === "pending" && streaming ? (
                // Hidden from the live region: screen readers get the finished
                // answer once, not every piece.
                <div className="d-chat d-chat-start">
                    <p
                        aria-hidden
                        className={`text-sm break-words whitespace-pre-wrap ${bubbleClass("assistant")}`}
                    >
                        {streaming}
                        <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-base-content/70 align-middle" />
                    </p>
                </div>
            ) : null}
            {status === "pending" && streaming ? (
                <span className="sr-only">{t("chat.writing")}</span>
            ) : null}

            {status === "pending" && !streaming ? (
                <div className="d-chat d-chat-start">
                    <p className="d-chat-bubble bg-base-200" aria-label={t("chat.writing")}>
                        <span className="d-loading d-loading-dots d-loading-sm" />
                    </p>
                </div>
            ) : null}

            {status === "refused" && error ? (
                <div className="d-chat d-chat-start">
                    <p role="status" className="d-chat-bubble max-w-[min(100%,36rem)] bg-base-200 text-sm">
                        {error}
                    </p>
                </div>
            ) : null}

            {status === "error" && error ? (
                <div className="d-alert d-alert-error mr-auto max-w-[min(100%,36rem)] text-sm">
                    <p>{error}</p>
                    <button type="button" className="d-btn d-btn-sm" onClick={onRetry}>
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
        <button
            type="button"
            className={ICON_BUTTON}
            aria-label={label}
            title={label}
            onClick={() => void copy()}
        >
            {copied === "copied" ? <Check className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
        </button>
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
                <button
                    key={value}
                    type="button"
                    aria-label={label}
                    aria-pressed={rating === value}
                    className={cn(ICON_BUTTON, rating === value && "text-base-content")}
                    onClick={() => onRate(rating === value ? null : value)}
                >
                    <Icon className={cn("size-3.5", rating === value && "fill-current")} aria-hidden />
                </button>
            ))}
            <span className="sr-only">{t("chat.rating.hint")}</span>
        </div>
    );
}
