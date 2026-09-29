import {api} from "@/shared/lib/api/client";
import type {SystemStatus} from "@pages/system/model/system";

export async function getSystemStatus(): Promise<SystemStatus> {
    const {data} = await api.get<SystemStatus>("/system/status");
    return data;
}
