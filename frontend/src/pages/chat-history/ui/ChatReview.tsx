import {ArrowLeft, ThumbsDown, ThumbsUp} from "lucide-react";
import {useEffect, useState} from "react";
import {Link, useLocation, useNavigate, useParams} from "react-router";


import {Card} from "@/components/ui/card";
import {chatMessageAnchor} from "@/entities/chat/model";
import {SourceList} from "@/entities/chat/SourceList";
import type {UserDetailLinkState} from "@/entities/user/model";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {localeIntlTag} from "@/shared/i18n/messages";
import {can} from "@/shared/lib/api/me";
import {useRequest} from "@/shared/lib/hooks/useRequest";
import {formatDateTime} from "@/shared/lib/time";
import {DeleteButton} from "@/shared/ui/DeleteButton";
import {StatusCard} from "@/shared/ui/StatusCard";
import {cn} from "cn";
import {getReviewedConversation} from "@pages/chat-history/api/chatHistory";
import {ChatDeleteDialog} from "@pages/chat-history/ui/ChatDeleteDialog";

/** One user's saved chat, read-only. */
export function ChatReview() {
    const {t, locale} = useI18n();
    const location = useLocation();
    const conversationId = Number(useParams().conversationId);
    const backTo = (location.state as UserDetailLinkState | null)?.from ?? "/chat-history";
    const {status, data, error, reload} = useRequest(
        String(conversationId),
        () => getReviewedConversation(conversationId),
        t("chatHistory.chatLoadError"),
    );
    const tag = localeIntlTag(locale);
    const navigate = useNavigate();
    const [deleting, setDeleting] = useState(false);
    // Opened at one message (from the answer ratings): scrolled to and marked.
    const focused = location.hash.slice(1);
    useEffect(() => {
        if (status === "ready" && focused) {
            document.getElementById(focused)?.scrollIntoView({block: "center"});
        }
    }, [status, focused]);

    const back = (
        <Link
            to={backTo}
            className="inline-flex w-fit items-center gap-1.5 text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
            <ArrowLeft className="size-4" aria-hidden />
            {t("userDetail.back")}
        </Link>
    );

    if (status !== "ready" || data == null) {
        return (
            <div className="stack stack--lg w-full">
                {back}
                {status === "loading" ? (
                    <p className="text-muted-foreground">{t("chatHistory.loading")}</p>
                ) : (
                    <StatusCard
                        title={t("chatHistory.chatLoadErrorTitle")}
                        detail={error}
                        onRetry={reload}
                    />
                )}
            </div>
        );
    }

    const linkState: UserDetailLinkState = {from: location.pathname};
    return (
        <div className="stack stack--lg w-full min-w-0">
            {back}
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="stack min-w-0">
                    <h1 className="break-words">{data.title}</h1>
                    <p className="text-sm text-muted-foreground">
                        {can("users.view") ? (
                            <Link
                                to={`/users/${data.user.id}`}
                                state={linkState}
                                className="underline-offset-2 hover:underline"
                            >
                                {data.user.name || data.user.email}
                            </Link>
                        ) : (
                            data.user.name || data.user.email
                        )}
                        {" · "}
                        {data.user.email}
                    </p>
                </div>
                {can("chat.purge") ? (
                    <DeleteButton size="default" className="self-start" onClick={() => setDeleting(true)}>
                        {t("chatHistory.delete.action")}
                    </DeleteButton>
                ) : null}
            </div>
            <ChatDeleteDialog
                chat={deleting ? {id: data.id, userName: data.user.name || data.user.email} : null}
                onClose={() => setDeleting(false)}
                // Gone: back where the reviewer came from.
                onDeleted={() => void navigate(backTo, {replace: true})}
            />
            <Card className="gap-3 px-4 py-4" aria-label={t("chat.conversation")}>
                {data.messages.map((message) => (
                    <div
                        key={message.id}
                        id={chatMessageAnchor(message.id)}
                        className={cn(
                            "space-y-1.5",
                            focused === chatMessageAnchor(message.id) && "-mx-2 rounded-xl p-2 ring-2 ring-ring/50",
                        )}
                    >
                        <p className="text-xs text-muted-foreground">
                            {message.role === "user" ? data.user.name || data.user.email : t("chat.title")}
                            {" · "}
                            {formatDateTime(message.created_at, tag)}
                        </p>
                        <p
                            className={cn(
                                "rounded-2xl px-3.5 py-2.5 text-sm break-words whitespace-pre-wrap",
                                message.role === "user"
                                    ? "ml-auto max-w-[min(100%,36rem)] bg-primary text-primary-foreground"
                                    : "mr-auto max-w-[min(100%,48rem)] bg-muted",
                            )}
                        >
                            {message.content}
                        </p>
                        {message.sources.length ? <SourceList sources={message.sources} answer={message.content} /> : null}
                        {message.rating ? (
                            <p className="flex items-center gap-1 text-xs text-muted-foreground">
                                {message.rating === "up" ? (
                                    <ThumbsUp className="size-3.5" aria-hidden />
                                ) : (
                                    <ThumbsDown className="size-3.5" aria-hidden />
                                )}
                                {message.rating === "up" ? t("chat.rating.good") : t("chat.rating.bad")}
                            </p>
                        ) : null}
                    </div>
                ))}
            </Card>
        </div>
    );
}
