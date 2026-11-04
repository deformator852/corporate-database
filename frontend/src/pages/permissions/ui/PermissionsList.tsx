import {TableCell, TableRow} from "@/components/ui/table";
import {getPermissionsPage} from "@/entities/permission/api";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {usePageParam} from "@/shared/lib/hooks/usePageParam";
import {useRequest} from "@/shared/lib/hooks/useRequest";
import {DataTable} from "@/shared/ui/DataTable";
import {ListPagination} from "@/shared/ui/ListPagination";
import {PageHeader} from "@/shared/ui/PageHeader";
import {StatusCard} from "@/shared/ui/StatusCard";

export function PermissionsList() {
    const {t} = useI18n();
    const [page, goToPage] = usePageParam();
    const {status, data, error, reload} = useRequest(
        String(page),
        () => getPermissionsPage(page),
        t("permissions.loadError"),
    );
    const items = data?.items ?? [];

    return (
        <div className="stack stack--lg w-full">
            <PageHeader id="permissions-heading" title={t("permissions.title")} subtitle={t("permissions.subtitle")}/>

            {status === "error" ? (
                <StatusCard title={t("permissions.loadErrorTitle")} detail={error} onRetry={reload} />
            ) : status === "ready" && data?.total === 0 ? (
                <StatusCard title={t("permissions.emptyTitle")} />
            ) : (
                <div className="stack">
                    <DataTable
                        aria-labelledby="permissions-heading"
                        columns={[
                            {label: t("common.name"), className: "px-4"},
                            {label: t("common.key")},
                            {label: t("permissions.table.roles"), className: "px-4"},
                        ]}
                        loading={status === "loading"}
                        loadingText={t("permissions.loading")}
                    >
                        {items.map((permission) => {
                            const roleNames = permission.roles.map((role) => role.name).join(", ");
                            return (
                                <TableRow key={permission.key}>
                                    <TableCell className="px-4 font-medium">{permission.name}</TableCell>
                                    <TableCell className="text-base-content/70">{permission.key}</TableCell>
                                    <TableCell className="max-w-xs truncate px-4" title={roleNames || undefined}>
                                        {roleNames || t("common.noDataDash")}
                                    </TableCell>
                                </TableRow>
                            );
                        })}
                    </DataTable>

                    {data ? (
                        <ListPagination
                            page={page}
                            pages={data.pages}
                            perPage={data.per_page}
                            total={data.total}
                            shown={items.length}
                            onPageChange={goToPage}
                        />
                    ) : null}
                </div>
            )}
        </div>
    );
}
