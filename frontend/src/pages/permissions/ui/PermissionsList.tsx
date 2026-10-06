import {Card} from "@/components/ui/card";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {usePageParam} from "@/shared/lib/hooks/usePageParam";
import {useRequest} from "@/shared/lib/hooks/useRequest";
import {ListPagination} from "@/shared/ui/ListPagination";
import {StatusCard} from "@/shared/ui/StatusCard";
import {getPermissionsPage} from "@/entities/permission/api";

export function PermissionsList() {
    const {t} = useI18n();
    const [page, goToPage] = usePageParam();
    const {status, data, error, reload} = useRequest(
        String(page),
        () => getPermissionsPage(page),
        t("permissions.loadError"),
    );
    const items = data?.items ?? [];
    const total = data?.total ?? 0;

    return (
        <div className="stack stack--lg w-full">
            <div className="stack">
                <h1 id="permissions-heading">{t("permissions.title")}</h1>
                <p className="max-w-xl text-muted-foreground">
                    {t("permissions.subtitle")}
                </p>
            </div>

            {status === "error" ? (
                <StatusCard title={t("permissions.loadErrorTitle")} detail={error} onRetry={reload} />
            ) : status === "ready" && total === 0 ? (
                <StatusCard title={t("permissions.emptyTitle")} />
            ) : (
                <div className="stack">
                    <Card className="gap-0 py-0">
                        <Table aria-labelledby="permissions-heading">
                            <TableHeader>
                                <TableRow className="hover:bg-transparent">
                                    <TableHead className="px-4">{t("common.name")}</TableHead>
                                    <TableHead>{t("common.key")}</TableHead>
                                    <TableHead className="px-4">
                                        {t("permissions.table.roles")}
                                    </TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {status === "loading" ? (
                                    <TableRow className="hover:bg-transparent">
                                        <TableCell
                                            colSpan={3}
                                            className="px-4 py-8 text-muted-foreground"
                                        >
                                            {t("permissions.loading")}
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    items.map((permission) => {
                                        const roleNames = permission.roles
                                            .map((role) => role.name)
                                            .join(", ");
                                        return (
                                            <TableRow key={permission.key}>
                                                <TableCell className="px-4 font-medium">
                                                    {permission.name}
                                                </TableCell>
                                                <TableCell className="text-muted-foreground">
                                                    {permission.key}
                                                </TableCell>
                                                <TableCell
                                                    className="max-w-xs truncate px-4"
                                                    title={roleNames || undefined}
                                                >
                                                    {roleNames || t("common.noDataDash")}
                                                </TableCell>
                                            </TableRow>
                                        );
                                    })
                                )}
                            </TableBody>
                        </Table>
                    </Card>

                    {data ? (
                        <ListPagination
                            page={page}
                            pages={data.pages}
                            perPage={data.per_page}
                            total={total}
                            shown={items.length}
                            onPageChange={goToPage}
                        />
                    ) : null}
                </div>
            )}
        </div>
    );
}
