import {api} from "@/shared/lib/api/client";
import type {SystemStatus} from "@pages/system/model/system";

/** The worker cuts the outdated documents again, one at a time; returns how
 * many. They stay searchable meanwhile. */
export async function rechunkDocuments(): Promise<number> {
    const {data} = await api.post<{documents: number}>("/system/rechunk");
    return data.documents;
}

export async function getSystemStatus(): Promise<SystemStatus> {
    const {data} = await api.get<SystemStatus>("/system/status");
    return data;
}
