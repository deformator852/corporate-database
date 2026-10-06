import {useState} from "react";
import {Pencil, Plus, Trash2} from "lucide-react";

import {Button} from "@/components/ui/button";
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
import {can} from "@/shared/lib/api/me";
import {getRolesPage} from "@/entities/role/api";
import {
    type RoleListItem,
} from "@/entities/role/model";
import {ConfirmDialog} from "@/shared/ui/ConfirmDialog";
import {deleteRole} from "@/entities/role/api";
import {RoleFormDialog} from "@pages/roles/ui/RoleFormDialog";

export function RolesList() {
    const {t} = useI18n();
    const [page, goToPage] = usePageParam();

    const canCreate = can("roles.create");
    const canUpdate = can("roles.update");
    const canDelete = can("roles.delete");
    const showActions = canUpdate || canDelete;
    const [formOpen, setFormOpen] = useState(false);
    const [editingRole, setEditingRole] = useState<RoleListItem | null>(null);
    const [deletingRole, setDeletingRole] = useState<RoleListItem | null>(null);

    const {status, data, error, reload} = useRequest(String(page), () => getRolesPage(page), t("roles.loadError"));
    const items = data?.items ?? [];
    const total = data?.total ?? 0;

    const openCreate = () => {
        setEditingRole(null);
        setFormOpen(true);
    };

    const openEdit = (role: RoleListItem) => {
        setEditingRole(role);
        setFormOpen(true);
    };

    const handleSaved = () => {
        reload();
    };

    const handleDeleted = () => {
        if (items.length === 1 && page > 1) {
            goToPage(page - 1);
            return;
        }
        reload();
    };

    return (
        <div className="stack stack--lg w-full">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="stack">
                    <h1 id="roles-heading">{t("roles.title")}</h1>
                    <p className="max-w-xl text-muted-foreground">
                        {t("roles.subtitle")}
                    </p>
                </div>
                {canCreate ? (
                    <Button type="button" className="self-start" onClick={openCreate}>
                        <Plus aria-hidden/>
                        {t("roles.create")}
                    </Button>
                ) : null}
            </div>

            {status === "error" ? (
                <StatusCard title={t("roles.loadErrorTitle")} detail={error} onRetry={reload} />
            ) : status === "ready" && total === 0 ? (
                <StatusCard title={t("roles.emptyTitle")} detail={t("roles.emptyDescription")}>
                    {canCreate ? (
                        <Button type="button" onClick={openCreate}>
                            <Plus aria-hidden/>
                            {t("roles.create")}
                        </Button>
                    ) : null}
                </StatusCard>
            ) : (
                <div className="stack">
                    <Card className="gap-0 py-0">
                        <Table aria-labelledby="roles-heading">
                            <TableHeader>
                                <TableRow className="hover:bg-transparent">
                                    <TableHead className="px-4">{t("common.name")}</TableHead>
                                    <TableHead>{t("common.key")}</TableHead>
                                    <TableHead>{t("roles.table.permissions")}</TableHead>
                                    {showActions ? (
                                        <TableHead className="px-4 text-right">
                                            {t("common.actions")}
                                        </TableHead>
                                    ) : null}
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {status === "loading" ? (
                                    <TableRow className="hover:bg-transparent">
                                        <TableCell
                                            colSpan={showActions ? 4 : 3}
                                            className="px-4 py-8 text-muted-foreground"
                                        >
                                            {t("roles.loading")}
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    items.map((role) => {
                                        const permissionNames = role.permissions
                                            .map((permission) => permission.name)
                                            .join(", ");
                                        return (
                                            <TableRow key={role.key}>
                                                <TableCell className="px-4 font-medium">
                                                    {role.name}
                                                </TableCell>
                                                <TableCell className="text-muted-foreground">
                                                    {role.key}
                                                </TableCell>
                                                <TableCell
                                                    className="max-w-xs truncate"
                                                    title={permissionNames || undefined}
                                                >
                                                    {permissionNames || t("common.noDataDash")}
                                                </TableCell>
                                                {showActions ? (
                                                    <TableCell className="px-4">
                                                        <div className="flex justify-end gap-1">
                                                            {canUpdate ? (
                                                                <Button
                                                                    type="button"
                                                                    variant="ghost"
                                                                    size="sm"
                                                                    aria-label={t("roles.editAria", {
                                                                        name: role.name,
                                                                    })}
                                                                    onClick={() => openEdit(role)}
                                                                >
                                                                    <Pencil aria-hidden/>
                                                                    {t("common.edit")}
                                                                </Button>
                                                            ) : null}
                                                            {canDelete ? (
                                                                <Button
                                                                    type="button"
                                                                    variant="destructive"
                                                                    size="sm"
                                                                    aria-label={
                                                                        role.protected
                                                                            ? t("roles.cannotDeleteAdmin")
                                                                            : t("roles.deleteAria", {
                                                                                  name: role.name,
                                                                              })
                                                                    }
                                                                    disabled={role.protected}
                                                                    title={
                                                                        role.protected
                                                                            ? t("roles.cannotDeleteAdmin")
                                                                            : undefined
                                                                    }
                                                                    onClick={() =>
                                                                        setDeletingRole(role)
                                                                    }
                                                                >
                                                                    <Trash2 aria-hidden/>
                                                                    {t("common.delete")}
                                                                </Button>
                                                            ) : null}
                                                        </div>
                                                    </TableCell>
                                                ) : null}
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

            <RoleFormDialog
                key={editingRole?.key ?? "create"}
                open={formOpen}
                role={editingRole}
                onOpenChange={setFormOpen}
                onSaved={handleSaved}
            />
            <ConfirmDialog
                open={deletingRole != null}
                onOpenChange={(open) => {
                    if (!open) {
                        setDeletingRole(null);
                    }
                }}
                title={t("roles.delete.title", {name: deletingRole?.name ?? t("common.thisRole")})}
                description={t("roles.delete.description")}
                confirmLabel={t("roles.delete.confirm")}
                pendingLabel={t("common.deleting")}
                errorMessage={t("roles.delete.error")}
                onConfirm={async () => {
                    if (deletingRole) {
                        await deleteRole(deletingRole.key);
                        handleDeleted();
                    }
                }}
            />
        </div>
    );
}
