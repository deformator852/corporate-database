export const NOTIFICATIONS_PER_PAGE = 20;
export const NOTIFICATION_READ_BATCH_MS = 2000;

export const NOTIFICATION_TYPES = [
    "document.completed",
    "document.store_failed",
    "document.queue_failed",
    "document.process_failed",
] as const;

export type NotificationType = (typeof NOTIFICATION_TYPES)[number];

export type NotificationItem = {
    id: number;
    type: NotificationType;
    message: string;
    read: boolean;
    created_at: string;
};

export type NotificationListPage = {
    items: NotificationItem[];
    page: number;
    per_page: number;
    total: number;
    pages: number;
    unread_count: number;
};

export function isNotificationType(value: string): value is NotificationType {
    return (NOTIFICATION_TYPES as readonly string[]).includes(value);
}

export function isNotificationItem(value: unknown): value is NotificationItem {
    if (value == null || typeof value !== "object") {
        return false;
    }
    const item = value as Partial<NotificationItem>;
    return (
        typeof item.id === "number" &&
        typeof item.type === "string" &&
        isNotificationType(item.type) &&
        typeof item.message === "string" &&
        typeof item.read === "boolean" &&
        typeof item.created_at === "string"
    );
}

export function formatNotificationTime(value: string, locale?: string): string {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }
    return new Intl.DateTimeFormat(locale, {
        dateStyle: "medium",
        timeStyle: "short",
    }).format(date);
}
