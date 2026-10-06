import {api} from "@/shared/lib/api/client";
import {AUDIT_PER_PAGE, type AuditListPage} from "@/entities/audit/model";

export async function getAuditPage(
    page: number,
    q = "",
    action = "",
    perPage = AUDIT_PER_PAGE,
): Promise<AuditListPage> {
    const {data} = await api.get<AuditListPage>("/audit", {
        params: {
            page,
            per_page: perPage,
            q: q || undefined,
            action: action || undefined,
        },
    });
    return data;
}
