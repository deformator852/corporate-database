import {apiSocketUrl} from "@/shared/lib/ws";

/** Search being rebuilt for a new embedding model: how far, in percent. */
export type ReindexProgress = {active: boolean; percent: number};

/** Sends the progress on connect, then each change (backend reindex_hub.py). */
export function reindexSocketUrl(): string {
    return apiSocketUrl("/system/reindex/ws");
}

export function isReindexProgress(value: unknown): value is ReindexProgress {
    const progress = value as Partial<ReindexProgress> | null;
    return typeof progress?.active === "boolean" && typeof progress.percent === "number";
}
