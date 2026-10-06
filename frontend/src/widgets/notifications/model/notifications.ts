import type {MessageKey} from "@/shared/i18n/messages";

export const NOTIFICATIONS_PER_PAGE = 20;
export const NOTIFICATION_READ_BATCH_MS = 2000;

const NOTIFICATION_TYPES = [
    "document.completed",
    "documents.completed",
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

function isNotificationType(value: string): value is NotificationType {
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

export function isFailure(type: NotificationType): boolean {
    return type.endsWith("_failed");
}

export {formatDateTime as formatNotificationTime, formatRelativeTime} from "@/shared/lib/time";

export function notificationTypeKey(type: NotificationType): MessageKey {
    return `notifications.type.${type}` as MessageKey;
}
