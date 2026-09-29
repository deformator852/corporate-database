import {api} from "@/shared/lib/api/client";
import {API_PREFIX} from "@/shared/lib/api/config";
import {
    NOTIFICATIONS_PER_PAGE,
    type NotificationListPage,
} from "@/widgets/notifications/model/notifications";

export async function getNotificationsPage(
    page: number,
    perPage = NOTIFICATIONS_PER_PAGE,
): Promise<NotificationListPage> {
    const {data} = await api.get<NotificationListPage>("/notifications", {
        params: {page, per_page: perPage},
    });
    return data;
}

export async function markNotificationsRead(
    ids: number[],
    options?: {keepalive?: boolean},
): Promise<void> {
    if (ids.length === 0) {
        return;
    }
    if (options?.keepalive) {
        const csrf = readCookie("csrf_access_token");
        const headers = new Headers({
            "Content-Type": "application/json",
        });
        if (csrf) {
            headers.set("X-CSRF-TOKEN", csrf);
        }
        await fetch(`${API_PREFIX}/notifications/read`, {
            method: "POST",
            credentials: "include",
            keepalive: true,
            headers,
            body: JSON.stringify({ids}),
        });
        return;
    }
    await api.post("/notifications/read", {ids});
}

export async function deleteNotification(id: number): Promise<void> {
    await api.delete(`/notifications/${id}`);
}

export async function clearNotifications(): Promise<void> {
    await api.delete("/notifications");
}

export function notificationsSocketUrl(): string {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/api/v1/notifications/ws`;
}

function readCookie(name: string): string | undefined {
    const prefix = `${name}=`;
    const row = document.cookie.split("; ").find((part) => part.startsWith(prefix));
    if (row == null) {
        return undefined;
    }
    return decodeURIComponent(row.slice(prefix.length));
}
