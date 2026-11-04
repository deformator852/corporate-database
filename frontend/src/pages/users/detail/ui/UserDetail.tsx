import {ArrowLeft, Eraser, MessagesSquare} from "lucide-react";
import {useCallback, useEffect, useMemo, useRef, useState} from "react";
import {Link, useLocation, useParams} from "react-router";

import {Badge} from "@/components/ui/badge";
import {Button, buttonVariants} from "@/components/ui/button";
import {Card} from "@/components/ui/card";
import {cn} from "cn";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {StatusCard} from "@/shared/ui/StatusCard";
import {can} from "@/shared/lib/api/me";
import {ChatPurgeDialog} from "@/widgets/chat-purge/ui/ChatPurgeDialog";
import type {ChatHistoryLinkState} from "@/entities/chat/model";
import {localeIntlTag} from "@/shared/i18n/messages";
import {getApiErrorCode, getApiErrorMessage} from "@/shared/lib/api/errors";
import type {AuditEntry} from "@/entities/audit/model";
import {actionLabel, describe} from "@/entities/audit/format";
import {getUser, getUserActivity} from "@pages/users/detail/api/user";
import type {UserDetailLinkState} from "@/entities/user/model";
import type {UserDetail as UserDetailData} from "@pages/users/detail/model/user";

type UserState =
    | {status: "loading"}
    | {status: "ready"; user: UserDetailData}
    | {status: "error"; message: string; missing: boolean};

type Feed = {
    items: AuditEntry[];
    // Next page cursor; null once the first recorded action is loaded.
    cursor: number | null;
    done: boolean;
    loading: boolean;
    error: string | null;
};

const EMPTY_FEED: Feed = {items: [], cursor: null, done: false, loading: false, error: null};

/** User page: profile and their audit history (infinite scroll). */
export function UserDetail() {
    const {userId} = useParams();
    // A new key per user resets all state when moving between users.
    return <UserDetailView key={userId} userId={Number(userId)} />;
}

function UserDetailView({userId}: {userId: number}) {
    const {t, locale} = useI18n();
    const backTo = (useLocation().state as UserDetailLinkState | null)?.from ?? "/users";
    const [user, setUser] = useState<UserState>({status: "loading"});
    const [feed, setFeed] = useState<Feed>(EMPTY_FEED);
    const [reloadKey, setReloadKey] = useState(0);
    const [purging, setPurging] = useState(false);
    const [purged, setPurged] = useState<string | null>(null);
    const sentinelRef = useRef<HTMLDivElement>(null);
    // Guards against the observer firing again before a page arrives.
    const loadingRef = useRef(false);

    const tag = localeIntlTag(locale);
    const dayFormat = useMemo(() => new Intl.DateTimeFormat(tag, {dateStyle: "long"}), [tag]);
    const timeFormat = useMemo(() => new Intl.DateTimeFormat(tag, {timeStyle: "medium"}), [tag]);
    const dateTimeFormat = useMemo(
        () => new Intl.DateTimeFormat(tag, {dateStyle: "medium", timeStyle: "short"}),
        [tag],
    );

    useEffect(() => {
        let cancelled = false;
        void getUser(userId)
            .then((data) => {
                if (!cancelled) {
                    setUser({status: "ready", user: data});
                }
            })
            .catch((reason) => {
                if (!cancelled) {
                    setUser({
                        status: "error",
                        missing: getApiErrorCode(reason) === "not_found",
                        message: getApiErrorMessage(reason, t("userDetail.loadError")),
                    });
                }
            });
        return () => {
            cancelled = true;
        };
    }, [userId, reloadKey, t]);

    const loadMore = useCallback(() => {
        if (loadingRef.current) {
            return;
        }
        loadingRef.current = true;
        setFeed((current) => ({...current, loading: true, error: null}));
        const before = feed.cursor;
        void getUserActivity(userId, before)
            .then((page) => {
                setFeed((current) => ({
                    items: [...current.items, ...page.items],
                    cursor: page.next_cursor,
                    done: page.next_cursor === null,
                    loading: false,
                    error: null,
                }));
            })
            .catch((reason) => {
                setFeed((current) => ({
                    ...current,
                    loading: false,
                    error: getApiErrorMessage(reason, t("userDetail.loadMoreError")),
                }));
            })
            .finally(() => {
                loadingRef.current = false;
            });
    }, [feed.cursor, userId, t]);

    const canLoad = user.status === "ready" && !feed.done && !feed.error;

    useEffect(() => {
        const sentinel = sentinelRef.current;
        if (!canLoad || sentinel == null) {
            return;
        }
        // Loads the next (older) page whenever the end of the list comes
        // within 400px of view; also fills a tall screen on first render.
        const observer = new IntersectionObserver(
            (entries) => {
                if (entries.some((entry) => entry.isIntersecting)) {
                    loadMore();
                }
            },
            {rootMargin: "400px 0px"},
        );
        observer.observe(sentinel);
        return () => observer.disconnect();
    }, [canLoad, loadMore]);

    const days = useMemo(() => {
        const groups: {day: string; entries: AuditEntry[]}[] = [];
        for (const entry of feed.items) {
            const day = dayFormat.format(new Date(entry.created_at));
            const last = groups.at(-1);
            if (last?.day === day) {
                last.entries.push(entry);
            } else {
                groups.push({day, entries: [entry]});
            }
        }
        return groups;
    }, [feed.items, dayFormat]);

    const back = (
        <Link
            to={backTo}
            className="inline-flex w-fit items-center gap-1.5 text-sm text-base-content/70 underline-offset-4 hover:text-base-content hover:underline"
        >
            <ArrowLeft className="size-4" aria-hidden />
            {t("userDetail.back")}
        </Link>
    );

    if (user.status === "loading") {
        return (
            <div className="stack stack--lg w-full">
                {back}
                <p className="text-base-content/70">{t("userDetail.loading")}</p>
            </div>
        );
    }

    if (user.status === "error") {
        return (
            <div className="stack stack--lg w-full">
                {back}
                {user.missing ? (
                    <StatusCard title={t("userDetail.notFound")} />
                ) : (
                    <StatusCard
                        title={t("userDetail.loadErrorTitle")}
                        detail={user.message}
                        onRetry={() => {
                            setUser({status: "loading"});
                            setReloadKey((key) => key + 1);
                        }}
                    />
                )}
            </div>
        );
    }

    const profile = user.user;
    const name = `${profile.first_name} ${profile.last_name}`.trim();
    const initials = `${profile.first_name.charAt(0)}${profile.last_name.charAt(0)}`.toUpperCase();
    const stats = [
        {label: t("userDetail.memberSince"), value: dateTimeFormat.format(new Date(profile.created_at))},
        {
            label: t("userDetail.lastSignIn"),
            value: profile.last_sign_in_at
                ? dateTimeFormat.format(new Date(profile.last_sign_in_at))
                : t("userDetail.never"),
        },
        {label: t("userDetail.actionsTotal"), value: profile.actions_total.toLocaleString(tag)},
    ];

    return (
        <div className="stack stack--lg w-full min-w-0">
            {back}

            <Card className="gap-4 px-4 py-4 sm:gap-5 sm:px-5 sm:py-5">
                <div className="flex min-w-0 items-center gap-3 sm:gap-4">
                    <div className="d-avatar d-avatar-placeholder shrink-0" aria-hidden>
                        <div className="size-12 rounded-full bg-primary text-base font-semibold text-primary-content sm:size-14 sm:text-lg">
                            {initials}
                        </div>
                    </div>
                    <div className="min-w-0 space-y-0.5">
                        <div className="flex min-w-0 items-center gap-2">
                            <h1 className="truncate text-xl sm:text-2xl">{name}</h1>
                            {profile.disabled ? (
                                <Badge variant="secondary">{t("users.disabled")}</Badge>
                            ) : null}
                        </div>
                        <p className="truncate text-sm text-base-content/70">{profile.email}</p>
                    </div>
                </div>

                <div className="flex flex-wrap items-center gap-1.5" aria-label={t("userDetail.roles")}>
                    {profile.roles.length > 0 ? (
                        profile.roles.map((role) => (
                            <span
                                key={role.key}
                                className="d-badge d-badge-sm bg-base-200 font-medium"
                            >
                                {role.name}
                            </span>
                        ))
                    ) : (
                        <span className="text-sm text-base-content/70">{t("userDetail.noRoles")}</span>
                    )}
                </div>

                {can("chat.history") || can("chat.purge") ? (
                    <div className="flex flex-wrap gap-2">
                        {can("chat.history") ? (
                            <Link
                                to={`/chat-history?user=${profile.id}`}
                                state={{userName: name || profile.email} satisfies ChatHistoryLinkState}
                                className={buttonVariants({variant: "outline", size: "sm"})}
                            >
                                <MessagesSquare aria-hidden />
                                {t("userDetail.viewChats")}
                            </Link>
                        ) : null}
                        {can("chat.purge") ? (
                            <Button type="button" variant="destructive" size="sm" onClick={() => setPurging(true)}>
                                <Eraser aria-hidden />
                                {t("chatPurge.open")}
                            </Button>
                        ) : null}
                    </div>
                ) : null}
                {purged ? (
                    <p role="status" className="text-sm text-base-content/70">
                        {purged}
                    </p>
                ) : null}

                <dl className="grid grid-cols-2 gap-3 border-t pt-4 lg:grid-cols-3">
                    {stats.map((stat) => (
                        <div key={stat.label} className="space-y-0.5">
                            <dt className="text-xs text-base-content/70">{stat.label}</dt>
                            <dd className="text-sm font-medium tabular-nums">{stat.value}</dd>
                        </div>
                    ))}
                </dl>
            </Card>

            <section className="stack" aria-labelledby="activity-heading">
                <h2 id="activity-heading" className="text-lg">
                    {t("userDetail.historyTitle")}
                </h2>

                {days.map((group) => (
                    <div key={group.day} className="space-y-2">
                        <h3 className="sticky top-0 z-10 bg-base-100/95 py-1 text-xs font-medium tracking-wide text-base-content/70 uppercase backdrop-blur">
                            {group.day}
                        </h3>
                        <ol className="list-none overflow-hidden rounded-box border border-base-300 bg-base-100 p-0">
                            {group.entries.map((entry) => {
                                const details = describe(t, entry);
                                const failed = entry.action === "auth.login_failed";
                                return (
                                    // Phone: time and IP on top, action below.
                                    // Wider: time | action | IP in one row.
                                    <li
                                        key={entry.id}
                                        className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 border-b px-4 py-3 last:border-b-0 sm:grid-cols-[6.5rem_minmax(0,1fr)_auto] sm:items-start sm:gap-x-4"
                                    >
                                        <time
                                            dateTime={entry.created_at}
                                            className="text-sm text-base-content/70 tabular-nums sm:col-start-1 sm:row-start-1"
                                        >
                                            {timeFormat.format(new Date(entry.created_at))}
                                        </time>
                                        <span className="justify-self-end text-xs text-base-content/70 tabular-nums sm:col-start-3 sm:row-start-1 sm:pt-0.5">
                                            {entry.ip ?? ""}
                                        </span>
                                        <div className="col-span-2 min-w-0 space-y-0.5 sm:col-span-1 sm:col-start-2 sm:row-start-1">
                                            <p
                                                className={cn(
                                                    "text-sm font-medium break-words",
                                                    failed && "text-error",
                                                )}
                                            >
                                                {actionLabel(t, entry.action)}
                                                {entry.target_label ? (
                                                    <span className="font-normal text-base-content">
                                                        {" · "}
                                                        {entry.target_label}
                                                    </span>
                                                ) : null}
                                            </p>
                                            {details ? (
                                                <p className="text-sm break-words text-base-content/70">
                                                    {details}
                                                </p>
                                            ) : null}
                                        </div>
                                    </li>
                                );
                            })}
                        </ol>
                    </div>
                ))}

                <div ref={sentinelRef} aria-hidden className="h-px" />

                <div role="status" className="py-2 text-center text-sm text-base-content/70">
                    {feed.loading ? (
                        t("userDetail.loadingMore")
                    ) : feed.error ? (
                        <span className="inline-flex flex-col items-center gap-2">
                            <span className="text-error">{feed.error}</span>
                            <Button type="button" size="sm" variant="outline" onClick={loadMore}>
                                {t("common.tryAgain")}
                            </Button>
                        </span>
                    ) : feed.done ? (
                        feed.items.length > 0 ? t("userDetail.end") : t("userDetail.empty")
                    ) : null}
                </div>
            </section>

            <ChatPurgeDialog
                open={purging}
                onOpenChange={setPurging}
                user={{id: profile.id, name: name || profile.email}}
                onPurged={(deleted) => setPurged(t("chatPurge.done", {count: deleted}))}
            />
        </div>
    );
}
