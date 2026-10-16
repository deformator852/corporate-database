import {useSessionStore} from "@/shared/auth/session-store";
import {refreshSession} from "@/shared/lib/api/client";
import {API_PREFIX} from "@/shared/lib/api/config";
import {isUnauthorized} from "@/shared/lib/api/errors";

// Server close codes (backend/src/security.py).
const CLOSE_SESSION_ENDED = 4401;
const CLOSE_FORBIDDEN = 4403;
const RETRY_MS = 2000;
const FORBIDDEN_RETRY_MS = 30_000;

/**
 * Delay before reconnecting after `code`. On an ended session it first
 * refreshes the access token; if that fails the user is signed out and
 * null is returned (stop reconnecting).
 */
export async function reconnectDelay(code: number): Promise<number | null> {
    if (code === CLOSE_FORBIDDEN) {
        return FORBIDDEN_RETRY_MS;
    }
    if (code !== CLOSE_SESSION_ENDED) {
        return RETRY_MS;
    }
    try {
        await refreshSession();
        return 0;
    } catch (error) {
        if (isUnauthorized(error)) {
            useSessionStore.getState().clear();
            return null;
        }
        return RETRY_MS;
    }
}

/** `ws(s)://host/api/v1<path>`, the scheme following the page's. */
export function apiSocketUrl(path: string): string {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}${API_PREFIX}${path}`;
}

export type LiveSocket = {
    /** The socket now; null before the first one and after close(). */
    current: () => WebSocket | null;
    close: () => void;
};

/**
 * A socket that reconnects until closed. `onOpen` runs each time one opens;
 * `onDrop` each time one closes, before any reconnect.
 */
export function openSocket(
    url: string,
    {onMessage, onOpen, onDrop}: {onMessage: (data: string) => void; onOpen?: () => void; onDrop?: () => void},
): LiveSocket {
    let closed = false;
    let socket: WebSocket | null = null;
    let timer: number | undefined;

    const open = () => {
        if (closed) {
            return;
        }
        const next = new WebSocket(url);
        socket = next;
        next.addEventListener("open", () => onOpen?.());
        next.addEventListener("message", (event) => {
            if (typeof event.data === "string") {
                onMessage(event.data);
            }
        });
        next.addEventListener("close", (event) => {
            onDrop?.();
            if (closed || socket !== next) {
                return;
            }
            void reconnectDelay(event.code).then((delay) => {
                if (delay !== null && !closed) {
                    timer = window.setTimeout(open, delay);
                }
            });
        });
        next.addEventListener("error", () => {
            next.close();
        });
    };

    // Deferred so an immediate close() (React StrictMode remount) cancels it
    // instead of aborting a socket mid-handshake.
    timer = window.setTimeout(open, 0);

    return {
        current: () => socket,
        close: () => {
            closed = true;
            if (timer !== undefined) {
                window.clearTimeout(timer);
            }
            socket?.close();
            socket = null;
        },
    };
}

/**
 * A listen-only socket that reconnects until the returned function closes
 * it. `onReconnect` runs each time it is open again after a drop: events
 * sent while it was down are lost, so callers reload what they show.
 */
export function connectSocket(
    url: string,
    onMessage: (data: string) => void,
    onReconnect?: () => void,
): () => void {
    let wasOpen = false;
    return openSocket(url, {
        onMessage,
        onOpen: () => {
            if (wasOpen) {
                onReconnect?.();
            }
            wasOpen = true;
        },
    }).close;
}
