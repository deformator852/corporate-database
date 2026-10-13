import type {MessageKey} from "@/shared/i18n/messages";

export const ERROR_LOG_PER_PAGE = 25;
export const ERROR_LEVELS = ["warning", "error", "critical"] as const;
/** unhandled: a bug nothing caught ("Unhandled (bug)"); app: Corpus logged
 * it ("Handled"); library: a component Corpus uses failed ("System"; its warnings are
 * not kept).
 * Backend services/error_log.py. */
export const ERROR_CATEGORIES = ["unhandled", "app", "library"] as const;

export type ErrorLevel = (typeof ERROR_LEVELS)[number];

export type ErrorLogEntry = {
    id: number;
    created_at: string;
    level: string;
    logger: string;
    category: string;
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

export function categoryKey(category: string): MessageKey {
    return `errorLog.category.${category}` as MessageKey;
}

/** The filters the page reads from its address. */
export type ErrorLogFilters = {level: string; category: string};
