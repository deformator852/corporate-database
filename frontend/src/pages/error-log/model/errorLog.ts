import type {MessageKey} from "@/shared/i18n/messages";

export const ERROR_LOG_PER_PAGE = 25;
export const ERROR_LEVELS = ["warning", "error", "critical"] as const;
export const ERROR_SOURCES = ["backend", "worker"] as const;

export type ErrorLevel = (typeof ERROR_LEVELS)[number];
export type ErrorSource = (typeof ERROR_SOURCES)[number];

export type ErrorLogEntry = {
    id: number;
    created_at: string;
    level: string;
    source: string;
    logger: string;
    message: string;
    traceback: string | null;
};

export type ErrorLogPage = {
    items: ErrorLogEntry[];
    page: number;
    per_page: number;
    total: number;
    pages: number;
};

export function levelKey(level: string): MessageKey {
    return `errorLog.level.${level}` as MessageKey;
}

export function sourceKey(source: string): MessageKey {
    return `errorLog.source.${source}` as MessageKey;
}
