import {AxiosError, type AxiosResponse, type InternalAxiosRequestConfig} from "axios";

import {api} from "@/shared/lib/api/client";

/** A request the fake server received. */
export type ApiRequest = {
    method: string;
    path: string;
    params: Record<string, unknown>;
    body: unknown;
    headers: Record<string, unknown>;
    /** Values of `:name` segments in the matched route. */
    route: Record<string, string>;
};

type Reply = {status: number; data: unknown};
/** A fixed response body, or a function of the request (may return `reply(...)`). */
type Handler = ((request: ApiRequest) => unknown) | object | string;

/** An error response: `reply(403, {code, message})`. */
export function reply(status: number, data: unknown = {}): Reply {
    return {status, data, [REPLY]: true} as Reply;
}

const REPLY = Symbol("reply");

export function apiError(status: number, message: string, code = "invalid"): Reply {
    return reply(status, {code, message});
}

/**
 * Replaces the network under the app's axios client: the real API functions,
 * interceptors (CSRF, refresh on 401) and error handling run; only the server
 * is scripted. Routes registered later win; an unscripted request fails the test.
 */
export function mockApi() {
    const routes: {method: string; pattern: RegExp; names: string[]; handler: Handler}[] = [];
    const calls: ApiRequest[] = [];
    const unhandled: string[] = [];

    api.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
        const method = (config.method ?? "get").toUpperCase();
        const path = (config.url ?? "").split("?")[0];
        const body = typeof config.data === "string" ? JSON.parse(config.data) : config.data;
        const headers = Object.fromEntries(Object.entries(config.headers ?? {}));
        for (const route of [...routes].reverse()) {
            const match = route.method === method ? route.pattern.exec(path) : null;
            if (!match) {
                continue;
            }
            const request: ApiRequest = {
                method,
                path,
                params: config.params ?? {},
                body,
                headers,
                route: Object.fromEntries(route.names.map((name, i) => [name, match[i + 1]])),
            };
            calls.push(request);
            const result =
                typeof route.handler === "function" ? await route.handler(request) : route.handler;
            const {status, data} = isReply(result) ? result : {status: 200, data: result};
            const response: AxiosResponse = {data, status, statusText: "", headers: {}, config};
            if (status >= 400) {
                throw new AxiosError(`Request failed with status ${status}`, "ERR_BAD_REQUEST", config, null, response);
            }
            return response;
        }
        unhandled.push(`${method} ${path}`);
        throw new Error(`No mock for ${method} ${path}`);
    };

    return {
        calls,
        unhandled,
        on(method: string, path: string, handler: Handler = {}) {
            const names: string[] = [];
            const source = path.replace(/:(\w+)/g, (_, name: string) => {
                names.push(name);
                return "([^/]+)";
            });
            routes.push({method: method.toUpperCase(), pattern: new RegExp(`^${source}$`), names, handler});
            return this;
        },
        /** Requests to `method path`, in order. */
        sent(method: string, path: string): ApiRequest[] {
            return calls.filter((c) => c.method === method.toUpperCase() && c.path === path);
        },
    };
}

function isReply(value: unknown): value is Reply {
    return typeof value === "object" && value !== null && REPLY in value;
}

export type MockApi = ReturnType<typeof mockApi>;
