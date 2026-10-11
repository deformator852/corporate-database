import {api} from "@/shared/lib/api/client";
import {ERROR_LOG_PER_PAGE, type ErrorLogFilters, type ErrorLogPage} from "@pages/error-log/model/errorLog";

/** Warnings and errors of the backend and the worker, newest first. */
export async function getErrorLogPage(page: number, filters: ErrorLogFilters): Promise<ErrorLogPage> {
    // An empty filter is left out: every value.
    const chosen = Object.fromEntries(Object.entries(filters).filter(([, value]) => value));
    const {data} = await api.get<ErrorLogPage>("/system/errors", {
        params: {page, per_page: ERROR_LOG_PER_PAGE, ...chosen},
    });
    return data;
}
