import {api} from "@/shared/lib/api/client";
import {ERROR_LOG_PER_PAGE, type ErrorLogPage} from "@pages/error-log/model/errorLog";

/** Warnings and errors of the backend and the worker, newest first. */
export async function getErrorLogPage(page: number, level: string, source: string): Promise<ErrorLogPage> {
    const {data} = await api.get<ErrorLogPage>("/system/errors", {
        params: {page, per_page: ERROR_LOG_PER_PAGE, level: level || undefined, source: source || undefined},
    });
    return data;
}
