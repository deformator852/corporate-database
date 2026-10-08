import {api} from "@/shared/lib/api/client";

/** Search being rebuilt for a new embedding model: how far, in percent. */
export type ReindexProgress = {active: boolean; percent: number};

export async function getReindexProgress(): Promise<ReindexProgress> {
    const {data} = await api.get<ReindexProgress>("/system/reindex");
    return data;
}
