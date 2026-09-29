import {Bell, BellOff, CircleAlert, CircleCheck, X} from "lucide-react";
import {useCallback, useEffect, useState} from "react";

import {Button} from "@/components/ui/button";
import {Popover, PopoverContent, PopoverTrigger} from "@/components/ui/popover";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {notificationTypeKey} from "@/shared/i18n/keys";
import {localeIntlTag} from "@/shared/i18n/messages";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {connectSocket} from "@/shared/lib/ws";
import {cn} from "cn";
import {
    clearNotifications,
    deleteNotification,
    getNotificationsPage,
    notificationsSocketUrl,
} from "@/widgets/notifications/api/notifications";
import {
    formatNotificationTime,
    formatRelativeTime,
    isFailure,
    isNotificationItem,
    NOTIFICATIONS_PER_PAGE,
    type NotificationItem,
    type NotificationListPage,
} from "@/widgets/notifications/model/notifications";
import {useNotificationReadBatch} from "@/widgets/notifications/model/useNotificationReadBatch";

type LoadState =
    | {status: "ready"; data: NotificationListPage}
    | {status: "error"; message: string};

export function NotificationBell() {
    const {t, locale} = useI18n();
    const [open, setOpen] = useState(false);
    const [load, setLoad] = useState<LoadState | null>(null);
    const [loadingMore, setLoadingMore] = useState(false);
    // State, not a ref: the list mounts after the popover opens, and the
    // read observer must attach once it exists.
    const [list, setList] = useState<HTMLUListElement | null>(null);
    // Unread when the panel opened: stay highlighted as "new" until it closes,
    // even though they are marked read as soon as they are seen.
    const [fresh, setFresh] = useState<ReadonlySet<number>>(new Set());
    const {queue, flush} = useNotificationReadBatch();

    const data = load?.status === "ready" ? load.data : null;
    const unreadCount = data?.unread_count ?? 0;

    const loadPage = useCallback(async (page: number, append: boolean) => {
        const next = await getNotificationsPage(page);
        setLoad((current) => {
            if (!append || current?.status !== "ready") {
                return {status: "ready", data: next};
            }
            const seen = new Set(current.data.items.map((item) => item.id));
            return {
                status: "ready",
                data: {
                    ...next,
                    items: [
                        ...current.data.items,
                        ...next.items.filter((item) => !seen.has(item.id)),
                    ],
                },
            };
        });
    }, []);

    useEffect(() => {
        let cancelled = false;
        void getNotificationsPage(1)
            .then((next) => {
                if (!cancelled) {
                    setLoad({status: "ready", data: next});
                }
            })
            .catch((reason) => {
                if (!cancelled) {
                    setLoad({
                        status: "error",
                        message: getApiErrorMessage(
                            reason,
                            t("notifications.loadError"),
                        ),
                    });
                }
            });
        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        return connectSocket(notificationsSocketUrl(), (raw) => {
            let payload: unknown;
            try {
                payload = JSON.parse(raw);
            } catch {
                return;
            }
            if (!isNotificationItem(payload)) {
                return;
            }
            setLoad((current) => mergeIncoming(current, payload));
        });
    }, []);

    const unreadKey =
        data?.items
            .filter((item) => !item.read)
            .map((item) => item.id)
            .join(",") ?? "";

    useEffect(() => {
        const root = list;
        if (!open || root == null || unreadKey.length === 0) {
            return;
        }
        const seen = new Set<number>();
        const observer = new IntersectionObserver(
            (entries) => {
                for (const entry of entries) {
                    if (!entry.isIntersecting) {
                        continue;
                    }
                    const id = Number(entry.target.getAttribute("data-notification-id"));
                    if (!Number.isInteger(id) || seen.has(id)) {
                        continue;
                    }
                    seen.add(id);
                    queue(id);
                    setFresh((current) => new Set(current).add(id));
                    setLoad((current) => markLocalRead(current, id));
                }
            },
            {root, threshold: 0.6},
        );
        for (const node of root.querySelectorAll("[data-unread='true']")) {
            observer.observe(node);
        }
        return () => {
            observer.disconnect();
        };
    }, [open, list, unreadKey, queue]);

    async function handleClear() {
        try {
            await clearNotifications();
            setLoad((current) =>
                current?.status === "ready"
                    ? {
                          status: "ready",
                          data: {
                              ...current.data,
                              items: [],
                              total: 0,
                              pages: 0,
                              unread_count: 0,
                          },
                      }
                    : current,
            );
        } catch (reason) {
            setLoad({
                status: "error",
                message: getApiErrorMessage(reason, t("notifications.clearError")),
            });
        }
    }

    async function handleDismiss(id: number) {
        const before = load;
        setLoad((current) => removeLocal(current, id));
        try {
            await deleteNotification(id);
        } catch {
            setLoad(before);
        }
    }

    async function handleScroll() {
        if (
            list == null ||
            load?.status !== "ready" ||
            loadingMore ||
            load.data.page >= load.data.pages
        ) {
            return;
        }
        if (list.scrollHeight - list.scrollTop - list.clientHeight > 80) {
            return;
        }
        setLoadingMore(true);
        try {
            await loadPage(load.data.page + 1, true);
        } catch {
            // Keep the already loaded page; the next scroll can retry.
        } finally {
            setLoadingMore(false);
        }
    }

    const label =
        unreadCount > 0
            ? t("notifications.unread", {count: unreadCount})
            : t("notifications.label");

    return (
        <Popover
            open={open}
            onOpenChange={(next) => {
                setOpen(next);
                if (!next) {
                    flush(true);
                    setFresh(new Set());
                }
            }}
        >
            <PopoverTrigger
                render={
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="relative"
                        aria-label={label}
                    />
                }
            >
                <Bell />
                {unreadCount > 0 ? (
                    <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] leading-none font-semibold text-destructive-foreground ring-2 ring-background">
                        {unreadCount > 9 ? "9+" : unreadCount}
                    </span>
                ) : null}
            </PopoverTrigger>
            <PopoverContent
                align="end"
                className="w-96 max-w-[calc(100vw-1.5rem)] overflow-hidden p-0"
                aria-label={t("notifications.label")}
            >
                <div className="flex items-center justify-between gap-2 border-b px-4 py-3">
                    <div className="flex items-center gap-2">
                        <p className="font-semibold">{t("notifications.label")}</p>
                        {unreadCount > 0 ? (
                            <span className="rounded-full bg-primary px-1.5 py-0.5 text-[11px] leading-none font-semibold text-primary-foreground tabular-nums">
                                {unreadCount}
                            </span>
                        ) : null}
                    </div>
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="text-muted-foreground"
                        disabled={!data || data.total === 0}
                        onClick={() => {
                            void handleClear();
                        }}
                    >
                        {t("notifications.clearAll")}
                    </Button>
                </div>
                {load?.status === "error" ? (
                    <div className="flex flex-col items-start gap-3 px-4 py-5">
                        <p className="text-sm text-muted-foreground">{load.message}</p>
                        <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => {
                                void loadPage(1, false).catch((reason) => {
                                    setLoad({
                                        status: "error",
                                        message: getApiErrorMessage(
                                            reason,
                                            t("notifications.loadError"),
                                        ),
                                    });
                                });
                            }}
                        >
                            {t("common.tryAgain")}
                        </Button>
                    </div>
                ) : !data || data.items.length === 0 ? (
                    load == null ? (
                        <p className="px-4 py-8 text-center text-sm text-muted-foreground">
                            {t("notifications.loading")}
                        </p>
                    ) : (
                        <div className="flex flex-col items-center gap-2 px-6 py-10 text-center">
                            <span className="flex size-11 items-center justify-center rounded-full bg-muted text-muted-foreground">
                                <BellOff className="size-5" aria-hidden />
                            </span>
                            <p className="font-medium">{t("notifications.empty")}</p>
                            <p className="text-sm text-muted-foreground">
                                {t("notifications.emptyHint")}
                            </p>
                        </div>
                    )
                ) : (
                    <ul
                        ref={setList}
                        className="max-h-[min(26rem,70vh)] list-none overflow-y-auto overscroll-contain p-0"
                        onScroll={handleScroll}
                    >
                        {data.items.map((item) => {
                            const failed = isFailure(item.type);
                            const isNew = !item.read || fresh.has(item.id);
                            const Icon = failed ? CircleAlert : CircleCheck;
                            return (
                                <li
                                    key={item.id}
                                    data-notification-id={item.id}
                                    data-unread={item.read ? undefined : "true"}
                                    className={cn(
                                        "group relative flex gap-3 border-b px-4 py-3 transition-colors last:border-b-0 hover:bg-muted/60",
                                        isNew && "bg-primary/5",
                                    )}
                                >
                                    <span
                                        className={cn(
                                            "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full",
                                            failed
                                                ? "bg-destructive/10 text-destructive"
                                                : "bg-success/10 text-success",
                                        )}
                                        aria-hidden
                                    >
                                        <Icon className="size-4" />
                                    </span>
                                    <div className="min-w-0 flex-1 pr-6">
                                        <p className="flex items-center gap-1.5 font-medium">
                                            {isNew ? (
                                                <span
                                                    className="size-2 shrink-0 rounded-full bg-primary"
                                                    aria-label={t("notifications.new")}
                                                />
                                            ) : null}
                                            <span className="truncate">
                                                {t(notificationTypeKey(item.type))}
                                            </span>
                                        </p>
                                        <p className="mt-0.5 text-sm break-words text-muted-foreground">
                                            {item.message}
                                        </p>
                                        <time
                                            dateTime={item.created_at}
                                            title={formatNotificationTime(
                                                item.created_at,
                                                localeIntlTag(locale),
                                            )}
                                            className="mt-1 block text-xs text-muted-foreground"
                                        >
                                            {formatRelativeTime(
                                                item.created_at,
                                                localeIntlTag(locale),
                                            )}
                                        </time>
                                    </div>
                                    <button
                                        type="button"
                                        aria-label={t("notifications.dismiss")}
                                        title={t("notifications.dismiss")}
                                        onClick={() => {
                                            void handleDismiss(item.id);
                                        }}
                                        className="absolute top-2.5 right-2.5 flex size-7 cursor-pointer items-center justify-center rounded-md text-muted-foreground opacity-0 transition-opacity outline-none group-hover:opacity-100 hover:bg-muted hover:text-foreground focus-visible:opacity-100 focus-visible:ring-3 focus-visible:ring-ring/50 [@media(hover:none)]:opacity-100"
                                    >
                                        <X className="size-4" aria-hidden />
                                    </button>
                                </li>
                            );
                        })}
                    </ul>
                )}
            </PopoverContent>
        </Popover>
    );
}

function mergeIncoming(
    current: LoadState | null,
    incoming: NotificationItem,
): LoadState | null {
    if (current == null || current.status !== "ready") {
        return {
            status: "ready",
            data: {
                items: [incoming],
                page: 1,
                per_page: NOTIFICATIONS_PER_PAGE,
                total: 1,
                pages: 1,
                unread_count: incoming.read ? 0 : 1,
            },
        };
    }
    if (current.data.items.some((item) => item.id === incoming.id)) {
        return current;
    }
    return {
        status: "ready",
        data: {
            ...current.data,
            items: [incoming, ...current.data.items],
            total: current.data.total + 1,
            unread_count: incoming.read
                ? current.data.unread_count
                : current.data.unread_count + 1,
        },
    };
}

function markLocalRead(current: LoadState | null, id: number): LoadState | null {
    if (current == null || current.status !== "ready") {
        return current;
    }
    const index = current.data.items.findIndex((item) => item.id === id);
    if (index < 0 || current.data.items[index].read) {
        return current;
    }
    const items = current.data.items.slice();
    items[index] = {...items[index], read: true};
    return {
        status: "ready",
        data: {
            ...current.data,
            items,
            unread_count: Math.max(0, current.data.unread_count - 1),
        },
    };
}

function removeLocal(current: LoadState | null, id: number): LoadState | null {
    if (current == null || current.status !== "ready") {
        return current;
    }
    const removed = current.data.items.find((item) => item.id === id);
    if (removed == null) {
        return current;
    }
    return {
        status: "ready",
        data: {
            ...current.data,
            items: current.data.items.filter((item) => item.id !== id),
            total: Math.max(0, current.data.total - 1),
            unread_count: removed.read
                ? current.data.unread_count
                : Math.max(0, current.data.unread_count - 1),
        },
    };
}
