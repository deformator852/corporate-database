import {useEffect, useEffectEvent, useState} from "react";

import {useI18n} from "@/shared/i18n/I18nProvider";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {connectSocket} from "@/shared/lib/ws";
import {
    clearNotifications,
    deleteNotification,
    getNotificationsPage,
    notificationsSocketUrl,
} from "@/widgets/notifications/api/notifications";
import {
    isNotificationItem,
    NOTIFICATIONS_PER_PAGE,
    type NotificationItem,
    type NotificationListPage,
} from "@/widgets/notifications/model/notifications";

type LoadState = {status: "ready"; data: NotificationListPage} | {status: "error"; message: string};

/** The user's notifications: loaded page by page, kept up to date by the
 * live socket, with local changes applied at once (read, dismissed). */
export function useNotificationFeed() {
    const {t} = useI18n();
    const [load, setLoad] = useState<LoadState | null>(null);
    const [loadingMore, setLoadingMore] = useState(false);

    const failed = (reason: unknown) => getApiErrorMessage(reason, t("notifications.loadError"));

    const loadFirst = (isCurrent: () => boolean = () => true) =>
        getNotificationsPage(1)
            .then((data) => isCurrent() && setLoad({status: "ready", data}))
            .catch((reason: unknown) => isCurrent() && setLoad({status: "error", message: failed(reason)}));
    const loadFirstOnMount = useEffectEvent(loadFirst);

    useEffect(() => {
        let current = true;
        void loadFirstOnMount(() => current);
        return () => {
            current = false;
        };
    }, []);

    useEffect(
        () =>
            connectSocket(notificationsSocketUrl(), (raw) => {
                let payload: unknown;
                try {
                    payload = JSON.parse(raw);
                } catch {
                    return;
                }
                if (isNotificationItem(payload)) {
                    setLoad((current) => mergeIncoming(current, payload));
                }
            }),
        [],
    );

    const data = load?.status === "ready" ? load.data : null;

    return {
        data,
        error: load?.status === "error" ? load.message : null,
        loading: load == null,
        retry: () => void loadFirst(),
        markRead: (id: number) => setLoad((current) => markLocalRead(current, id)),
        async clear() {
            try {
                await clearNotifications();
                setLoad((current) =>
                    current?.status === "ready"
                        ? {status: "ready", data: {...current.data, items: [], total: 0, pages: 0, unread_count: 0}}
                        : current,
                );
            } catch (reason) {
                setLoad({status: "error", message: getApiErrorMessage(reason, t("notifications.clearError"))});
            }
        },
        async dismiss(id: number) {
            const before = load;
            setLoad((current) => removeLocal(current, id));
            try {
                await deleteNotification(id);
            } catch {
                setLoad(before);
            }
        },
        async loadMore() {
            if (data == null || loadingMore || data.page >= data.pages) {
                return;
            }
            setLoadingMore(true);
            try {
                const next = await getNotificationsPage(data.page + 1);
                setLoad((current) => (current?.status === "ready" ? {status: "ready", data: appended(current.data, next)} : current));
            } catch {
                // Keep the pages already loaded; the next scroll retries.
            } finally {
                setLoadingMore(false);
            }
        },
    };
}

function appended(current: NotificationListPage, next: NotificationListPage): NotificationListPage {
    const seen = new Set(current.items.map((item) => item.id));
    return {...next, items: [...current.items, ...next.items.filter((item) => !seen.has(item.id))]};
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
