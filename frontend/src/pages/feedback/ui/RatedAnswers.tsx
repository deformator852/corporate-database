import {Link, useLocation} from "react-router";

import {Card} from "@/components/ui/card";
import {NativeSelect, NativeSelectOption} from "@/components/ui/native-select";
import type {AnswerRating} from "@/entities/chat/model";
import {SourceList} from "@/entities/chat/SourceList";
import type {UserDetailLinkState} from "@/entities/user/model";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {localeIntlTag} from "@/shared/i18n/messages";
import {can} from "@/shared/lib/api/me";
import {usePageParam} from "@/shared/lib/hooks/usePageParam";
import {useRequest} from "@/shared/lib/hooks/useRequest";
import {useUrlParams} from "@/shared/lib/hooks/useUrlParams";
import {formatDateTime} from "@/shared/lib/time";
import {ListPagination} from "@/shared/ui/ListPagination";
import {StatusCard} from "@/shared/ui/StatusCard";
import {getRatedAnswers} from "@pages/feedback/api/feedback";
import type {RatedAnswer} from "@pages/feedback/model/feedback";

/** Answers users rated, bad ones first, to see where the assistant goes wrong. */
export function RatedAnswers() {
    const {t} = useI18n();
    const [params, updateParams] = useUrlParams();
    const rating: AnswerRating = params.get("rating") === "up" ? "up" : "down";
    const [page] = usePageParam();
    const {status, data, error, reload} = useRequest(
        `${rating}:${page}`,
        () => getRatedAnswers(rating, page),
        t("feedback.loadError"),
    );
    const items = data?.items ?? [];

    return (
        <div className="stack stack--lg w-full">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
                <div className="stack">
                    <h1>{t("feedback.title")}</h1>
                    <p className="max-w-xl text-muted-foreground">{t("feedback.subtitle")}</p>
                </div>
                <NativeSelect
                    className="w-full sm:w-48"
                    aria-label={t("feedback.show")}
                    value={rating}
                    onChange={(event) => updateParams({rating: event.target.value, page: "1"})}
                >
                    <NativeSelectOption value="down">{t("feedback.bad")}</NativeSelectOption>
                    <NativeSelectOption value="up">{t("feedback.good")}</NativeSelectOption>
                </NativeSelect>
            </div>

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
                                <RatedAnswerCard item={item} />
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
                            onPageChange={(next) => updateParams({page: String(next)})}
                        />
                    ) : null}
                </div>
            )}
        </div>
    );
}

function RatedAnswerCard({item}: {item: RatedAnswer}) {
    const {t, locale} = useI18n();
    const location = useLocation();
    // The user page's Back link returns here.
    const linkState: UserDetailLinkState = {from: location.pathname + location.search};
    return (
        <Card className="gap-3 px-4 py-4">
            <p className="text-xs text-muted-foreground">
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
            {item.sources.length ? <SourceList sources={item.sources} /> : null}
        </Card>
    );
}
