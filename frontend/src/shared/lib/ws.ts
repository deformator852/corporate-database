import {useSessionStore} from "@/shared/auth/session-store";
import {refreshSession} from "@/shared/lib/api/client";
import {isUnauthorized} from "@/shared/lib/api/errors";

// Server close codes (backend/src/api/ws.py).
export const CLOSE_SESSION_ENDED = 4401;
export const CLOSE_FORBIDDEN = 4403;
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

export function connectSocket(
    url: string,
    onMessage: (data: string) => void,
): () => void {
    let closed = false;
    let socket: WebSocket | null = null;
    let timer: number | undefined;

    const open = () => {
        if (closed) {
            return;
        }
        const next = new WebSocket(url);
        socket = next;
        next.addEventListener("message", (event) => {
            if (typeof event.data === "string") {
                onMessage(event.data);
            }
        });
        next.addEventListener("close", (event) => {
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

    timer = window.setTimeout(open, 0);

    return () => {
        closed = true;
        if (timer !== undefined) {
            window.clearTimeout(timer);
        }
        socket?.close();
        socket = null;
    };
}
