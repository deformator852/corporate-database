import {Check, Copy, RefreshCw, ThumbsDown, ThumbsUp} from "lucide-react";
import {useEffect, useRef, useState, type ReactNode} from "react";

import {SourceList} from "@/entities/chat/SourceList";
import type {ChatMessage, ChatStatus} from "@pages/home/model/chat";
import type {AnswerRating} from "@/entities/chat/model";
import {cn} from "cn";
import {useSessionStore} from "@/shared/auth/session-store";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {LogoMark} from "@/shared/ui/Logo";

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

    const actions = (message: ChatMessage, index: number) => (
        <div className="flex flex-wrap items-center gap-0.5">
            <CopyAnswer text={message.content} />
            {/* Saved answers only: the server replaces it by id. */}
            {index === messages.length - 1 && message.messageId != null && status !== "pending" && onRegenerate ? (
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
                <RateAnswer rating={message.rating ?? null} onRate={(rating) => onRate(message, rating)} />
            ) : null}
            <span className="ml-1 text-xs text-base-content/70">{t("chat.aiGenerated")}</span>
        </div>
    );

    if (messages.length === 0 && status === "idle") {
        return (
            <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 px-6 py-10 text-center">
                <LogoMark className="size-12" />
                <p className="text-xl font-semibold tracking-tight">{t("chat.emptyTitle")}</p>
                <p className="max-w-md text-sm text-base-content/70">{t("chat.emptyDescription")}</p>
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
            className="min-h-0 flex-1 overflow-y-auto overscroll-contain"
            onScroll={onScroll}
        >
            <div className="flex flex-col py-2">
                {messages.map((message, index) => (
                    <Row key={message.id} role={message.role}>
                        <p
                            data-ai-generated={message.role === "assistant" ? "true" : undefined}
                            className="text-sm leading-6 break-words whitespace-pre-wrap"
                        >
                            {message.content}
                        </p>
                        {message.role === "assistant" && message.sources?.length ? (
                            <SourceList sources={message.sources} answer={message.content} />
                        ) : null}
                        {message.role === "assistant" ? actions(message, index) : null}
                    </Row>
                ))}

                {status === "pending" && streaming ? (
                    // Hidden from the live region: screen readers get the finished answer once.
                    <div aria-hidden>
                        <Row role="assistant">
                            <p className="text-sm leading-6 break-words whitespace-pre-wrap">
                                {streaming}
                                <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-base-content/70 align-middle" />
                            </p>
                        </Row>
                    </div>
                ) : null}
                {status === "pending" && streaming ? <span className="sr-only">{t("chat.writing")}</span> : null}
                {status === "pending" && !streaming ? (
                    <Row role="assistant">
                        <p className="flex h-6 items-center" aria-label={t("chat.writing")}>
                            <span className="d-loading d-loading-dots d-loading-sm" />
                        </p>
                    </Row>
                ) : null}
                {status === "refused" && error ? (
                    <Row role="assistant">
                        <p role="status" className="text-sm leading-6">
                            {error}
                        </p>
                    </Row>
                ) : null}
                {status === "error" && error ? (
                    <div className="px-4 py-3 md:px-6">
                        <div className="d-alert d-alert-error max-w-3xl text-sm">
                            <p>{error}</p>
                            <button type="button" className="d-btn d-btn-sm" onClick={onRetry}>
                                {t("chat.retry")}
                            </button>
                        </div>
                    </div>
                ) : null}
            </div>
        </div>
    );
}

/** One message of the log: who wrote it, then what they wrote. */
function Row({role, children}: {role: ChatMessage["role"]; children: ReactNode}) {
    const {t} = useI18n();
    const user = useSessionStore((state) => state.user);
    const initials = `${user?.first_name.charAt(0) ?? ""}${user?.last_name.charAt(0) ?? ""}`.toUpperCase();
    return (
        <div className="flex gap-3 px-4 py-3 hover:bg-base-200/40 md:px-6">
            {role === "user" ? (
                <div className="d-avatar d-avatar-placeholder shrink-0 self-start" aria-hidden>
                    <div className="size-8 rounded-full bg-base-200 text-xs font-medium">{initials}</div>
                </div>
            ) : (
                <LogoMark className="size-8" />
            )}
            <div className="flex max-w-3xl min-w-0 flex-1 flex-col gap-1.5">
                <div className="text-sm font-semibold select-none">{t(role === "user" ? "chat.you" : "chat.assistant")}</div>
                {children}
            </div>
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
