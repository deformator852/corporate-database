import axios, {
    type AxiosError,
    type InternalAxiosRequestConfig,
} from "axios";

import {useSessionStore} from "@/shared/auth/session-store";
import {API_PREFIX} from "@/shared/lib/api/config";
import {isUnauthorized} from "@/shared/lib/api/errors";

export const api = axios.create({
    baseURL: API_PREFIX,
    withCredentials: true,
});

const mutatingMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);

type RetryConfig = InternalAxiosRequestConfig & { _retry?: boolean };

let refreshRequest: Promise<void> | null = null;

api.interceptors.request.use((config) => {
    const method = config.method?.toUpperCase();
    if (!method || !mutatingMethods.has(method)) {
        return config;
    }

    const csrfCookie = isRefreshRequest(config)
        ? "csrf_refresh_token"
        : "csrf_access_token";
    const csrf = readCookie(csrfCookie);
    if (csrf) {
        config.headers.set("X-CSRF-TOKEN", csrf);
    }

    return config;
});

api.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
        const original = error.config as RetryConfig | undefined;
        if (
            original == null ||
            error.response?.status !== 401 ||
            original._retry ||
            isLoginRequest(original) ||
            isRefreshRequest(original)
        ) {
            return Promise.reject(error);
        }

        original._retry = true;

        try {
            await refreshSession();
            return api(original);
        } catch (refreshError) {
            if (isUnauthorized(refreshError)) {
                useSessionStore.getState().clear();
            }
            return Promise.reject(refreshError);
        }
    },
);

export function refreshSession(): Promise<void> {
    if (refreshRequest == null) {
        refreshRequest = oneTabAtATime(() => api.post("/auth/refresh").then(() => undefined)).finally(() => {
            refreshRequest = null;
        });
    }

    return refreshRequest;
}

/**
 * Each refresh token works once, and every tab shares it. When the access
 * token expires, the sockets of all tabs drop together and each tab
 * refreshes: run at once, all but the first would send the token the first
 * just used up and sign the user out. In turn, each sends the newest one.
 */
function oneTabAtATime<T>(work: () => Promise<T>): Promise<T> {
    const locks = typeof navigator === "undefined" ? undefined : navigator.locks;
    return locks ? locks.request("corpus-session-refresh", work) : work();
}

function isRefreshRequest(config: InternalAxiosRequestConfig): boolean {
    return requestPath(config).endsWith("/auth/refresh");
}

function isLoginRequest(config: InternalAxiosRequestConfig): boolean {
    return requestPath(config).endsWith("/auth/login");
}

function requestPath(config: InternalAxiosRequestConfig): string {
    const url = config.url ?? "";
    if (url.startsWith("http://") || url.startsWith("https://")) {
        return new URL(url).pathname;
    }

    const base = config.baseURL ?? "";
    if (base.startsWith("http://") || base.startsWith("https://")) {
        return new URL(url, base).pathname;
    }

    const joined = `${base}/${url}`.replace(/\/{2,}/g, "/");
    return joined.startsWith("/") ? joined : `/${joined}`;
}

function readCookie(name: string): string | undefined {
    const prefix = `${name}=`;
    const row = document.cookie.split("; ").find((part) => part.startsWith(prefix));
    if (row == null) {
        return undefined;
    }

    return decodeURIComponent(row.slice(prefix.length));
}
