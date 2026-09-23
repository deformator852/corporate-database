import {Bell} from "lucide-react";
import {useCallback, useEffect, useRef, useState} from "react";

import {Button} from "@/components/ui/button";
import {Popover, PopoverContent, PopoverTrigger} from "@/components/ui/popover";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {connectSocket} from "@/shared/lib/ws";
import {
    clearNotifications,
    getNotificationsPage,
    notificationsSocketUrl,
} from "@/widgets/notifications/api/notifications";
import {
    formatNotificationTime,
    isNotificationItem,
    NOTIFICATION_TYPE_LABELS,
    NOTIFICATIONS_PER_PAGE,
    type NotificationItem,
    type NotificationListPage,
} from "@/widgets/notifications/model/notifications";
import {useNotificationReadBatch} from "@/widgets/notifications/model/useNotificationReadBatch";

type LoadState =
    | {status: "ready"; data: NotificationListPage}
    | {status: "error"; message: string};

export function NotificationBell() {
    const [open, setOpen] = useState(false);
    const [load, setLoad] = useState<LoadState | null>(null);
    const [loadingMore, setLoadingMore] = useState(false);
    const listRef = useRef<HTMLUListElement>(null);
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
                            "Could not load notifications.",
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
        if (!open || unreadKey.length === 0) {
            return;
        }
        const root = listRef.current;
        if (root == null) {
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
    }, [open, unreadKey, queue]);

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
                message: getApiErrorMessage(reason, "Could not clear notifications."),
            });
        }
    }

    async function handleScroll() {
        const list = listRef.current;
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
        unreadCount > 0 ? `Notifications, ${unreadCount} unread` : "Notifications";

    return (
        <Popover
            open={open}
            onOpenChange={(next) => {
                setOpen(next);
                if (!next) {
                    flush(true);
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
                    <span
                        className="absolute top-1.5 right-1.5 size-2 rounded-full bg-destructive"
                        aria-hidden
                    />
                ) : null}
            </PopoverTrigger>
            <PopoverContent aria-label="Notifications">
                <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
                    <p className="font-medium">Notifications</p>
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={!data || data.total === 0}
                        onClick={() => {
                            void handleClear();
                        }}
                    >
                        Clear
                    </Button>
                </div>
                {load?.status === "error" ? (
                    <div className="stack px-3 py-4">
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
                                            "Could not load notifications.",
                                        ),
                                    });
                                });
                            }}
                        >
                            Try again
                        </Button>
                    </div>
                ) : !data || data.items.length === 0 ? (
                    <p className="px-3 py-6 text-sm text-muted-foreground">
                        {load == null ? "Loading notifications…" : "No notifications"}
                    </p>
                ) : (
                    <ul
                        ref={listRef}
                        className="max-h-80 overflow-y-auto"
                        onScroll={handleScroll}
                    >
                        {data.items.map((item) => (
                            <li
                                key={item.id}
                                data-notification-id={item.id}
                                data-unread={item.read ? undefined : "true"}
                                className="border-b px-3 py-2.5 last:border-b-0"
                            >
                                <p className="font-medium">
                                    {NOTIFICATION_TYPE_LABELS[item.type]}
                                </p>
                                <p className="text-sm text-muted-foreground">{item.message}</p>
                                <p className="mt-1 text-xs text-muted-foreground">
                                    <time dateTime={item.created_at}>
                                        {formatNotificationTime(item.created_at)}
                                    </time>
                                </p>
                            </li>
                        ))}
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
