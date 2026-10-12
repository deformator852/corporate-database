import {MessagesSquare, ThumbsDown, ThumbsUp} from "lucide-react";
import {useState} from "react";
import {Link, useLocation} from "react-router";

import {buttonVariants} from "@/components/ui/button";
import {Card} from "@/components/ui/card";
import {NativeSelect, NativeSelectOption} from "@/components/ui/native-select";
import {chatMessageAnchor} from "@/entities/chat/model";
import {SourceList} from "@/entities/chat/SourceList";
import type {UserDetailLinkState} from "@/entities/user/model";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {PageHeader} from "@/shared/ui/PageHeader";
import {localeIntlTag} from "@/shared/i18n/messages";
import {can} from "@/shared/lib/api/me";
import {refreshAfterDelete, usePageParam} from "@/shared/lib/hooks/usePageParam";
import {useRequest} from "@/shared/lib/hooks/useRequest";
import {useUrlParams} from "@/shared/lib/hooks/useUrlParams";
import {formatDateTime} from "@/shared/lib/time";
import {ListPagination} from "@/shared/ui/ListPagination";
import {ConfirmDialog} from "@/shared/ui/ConfirmDialog";
import {DeleteButton} from "@/shared/ui/DeleteButton";
import {StatusCard} from "@/shared/ui/StatusCard";
import {cn} from "cn";
import {getRatedAnswers, removeRating} from "@pages/feedback/api/feedback";
import {RATING_FILTERS, type RatedAnswer, type RatingFilter} from "@pages/feedback/model/feedback";

const FILTER_LABELS = {down: "feedback.bad", up: "feedback.good", all: "feedback.all"} as const;

/** Answers users rated, bad ones first, to see where the assistant goes wrong. */
export function RatedAnswers() {
    const {t} = useI18n();
    const [params, updateParams] = useUrlParams();
    // Bad answers first: those are the ones to act on.
    const rating = RATING_FILTERS.find((value) => value === params.get("rating")) ?? "down";
    const [page, goToPage] = usePageParam();
    const [removing, setRemoving] = useState<RatedAnswer | null>(null);
    const {status, data, error, reload} = useRequest(
        `${rating}:${page}`,
        () => getRatedAnswers(rating, page),
        t("feedback.loadError"),
    );
    const items = data?.items ?? [];

    return (
        <div className="stack stack--lg w-full">
            <PageHeader
                title={t("feedback.title")}
                subtitle={t("feedback.subtitle")}
                action={
                    <NativeSelect
                        className="w-full sm:w-48"
                        aria-label={t("feedback.show")}
                        value={rating}
                        onChange={(event) => updateParams({rating: event.target.value, page: "1"})}
                    >
                        {RATING_FILTERS.map((value: RatingFilter) => (
                            <NativeSelectOption key={value} value={value}>
                                {t(FILTER_LABELS[value])}
                            </NativeSelectOption>
                        ))}
                    </NativeSelect>
                }
            />

            {status === "error" ? (
                <StatusCard title={t("feedback.loadErrorTitle")} detail={error} onRetry={reload} />
            ) : status === "loading" ? (
                <p className="text-sm text-muted-foreground">{t("feedback.loading")}</p>
            ) : items.length === 0 ? (
                <StatusCard title={t("feedback.empty")} />
            ) : (
                <div className="stack">
                    <ul className="flex list-none flex-col gap-3 ps-0">
                        {items.map((item) => (
                            <li key={item.message_id}>
                                <RatedAnswerCard item={item} onRemove={() => setRemoving(item)} />
                            </li>
                        ))}
                    </ul>
                    {data ? (
                        <ListPagination
                            page={page}
                            pages={data.pages}
                            perPage={data.per_page}
                            total={data.total}
                            shown={items.length}
                            onPageChange={goToPage}
                        />
                    ) : null}
                </div>
            )}
            <ConfirmDialog
                open={removing != null}
                onOpenChange={(open) => {
                    if (!open) {
                        setRemoving(null);
                    }
                }}
                title={t("feedback.remove.title")}
                description={t("feedback.remove.description")}
                confirmLabel={t("common.delete")}
                pendingLabel={t("common.deleting")}
                errorMessage={t("feedback.remove.error")}
                onConfirm={async () => {
                    if (removing) {
                        await removeRating(removing.message_id);
                        refreshAfterDelete(page, items.length, goToPage, reload);
                    }
                }}
            />
        </div>
    );
}

function RatedAnswerCard({item, onRemove}: {item: RatedAnswer; onRemove: () => void}) {
    const {t, locale} = useI18n();
    const Thumb = item.rating === "down" ? ThumbsDown : ThumbsUp;
    const location = useLocation();
    // The user page's Back link returns here.
    const linkState: UserDetailLinkState = {from: location.pathname + location.search};
    return (
        <Card className="gap-3 px-4 py-4">
            <p className="flex flex-wrap items-center gap-x-1 text-xs text-muted-foreground">
                {/* Which way it was rated: needed once both kinds are listed. */}
                <Thumb
                    className={cn("size-3.5", item.rating === "down" ? "text-destructive" : "text-success")}
                    aria-label={t(item.rating === "down" ? "chat.rating.bad" : "chat.rating.good")}
                    role="img"
                />
                {formatDateTime(item.rated_at, localeIntlTag(locale))}
                {" · "}
                {item.user == null ? (
                    t("feedback.deletedUser")
                ) : can("users.view") ? (
                    <Link to={`/users/${item.user.id}`} state={linkState} className="underline-offset-2 hover:underline">
                        {item.user.name}
                    </Link>
                ) : (
                    item.user.name
                )}
            </p>
            <div className="stack">
                <p className="text-xs font-medium text-muted-foreground">{t("feedback.question")}</p>
                <p className="font-medium break-words whitespace-pre-wrap">{item.question}</p>
            </div>
            <div className="stack">
                <p className="text-xs font-medium text-muted-foreground">{t("feedback.answer")}</p>
                <p className="text-sm break-words whitespace-pre-wrap">{item.answer}</p>
            </div>
            {item.sources.length ? <SourceList sources={item.sources} answer={item.answer} /> : null}
            <div className="flex flex-wrap items-center justify-between gap-2">
                {can("chat.history") ? (
                    <Link
                        // The chat page scrolls to this answer; its Back link returns here.
                        to={`/chat-history/${item.conversation_id}#${chatMessageAnchor(item.message_id)}`}
                        state={linkState}
                        className={buttonVariants({variant: "outline", size: "sm"})}
                    >
                        <MessagesSquare aria-hidden />
                        {t("feedback.openChat")}
                    </Link>
                ) : null}
                <DeleteButton className="ms-auto" aria-label={t("feedback.removeAria")} onClick={onRemove} />
            </div>
        </Card>
    );
}
