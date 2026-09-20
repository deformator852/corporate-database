import {isAxiosError} from "axios";

type ApiErrorBody = {
    code?: string;
    message?: string;
};

export function getApiErrorMessage(
    error: unknown,
    fallback = "Something went wrong. Try again.",
): string {
    if (!isAxiosError<ApiErrorBody>(error)) {
        return fallback;
    }

    const message = error.response?.data?.message;
    if (typeof message === "string" && message.length > 0) {
        return message;
    }

    if (error.response == null) {
        return "Could not reach the server. Try again.";
    }

    return fallback;
}

export function getApiErrorCode(error: unknown): string | undefined {
    if (!isAxiosError<ApiErrorBody>(error)) {
        return undefined;
    }

    const code = error.response?.data?.code;
    return typeof code === "string" && code.length > 0 ? code : undefined;
}

export function isUnauthorized(error: unknown): boolean {
    return isAxiosError(error) && error.response?.status === 401;
}
