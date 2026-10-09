import {useState} from "react";
import {Pencil, Plus, Trash2} from "lucide-react";

import {Button} from "@/components/ui/button";
import {TableCell, TableRow} from "@/components/ui/table";
import {deleteRole, getRolesPage} from "@/entities/role/api";
import type {RoleListItem} from "@/entities/role/model";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {can} from "@/shared/lib/api/me";
import {refreshAfterDelete, usePageParam} from "@/shared/lib/hooks/usePageParam";
import {useRequest} from "@/shared/lib/hooks/useRequest";
import {ConfirmDialog} from "@/shared/ui/ConfirmDialog";
import {DataTable} from "@/shared/ui/DataTable";
import {ListPagination} from "@/shared/ui/ListPagination";
import {PageHeader} from "@/shared/ui/PageHeader";
import {StatusCard} from "@/shared/ui/StatusCard";
import {RoleFormDialog} from "@pages/roles/ui/RoleFormDialog";

/** What the signed-in user may do to the roles in the list. */
type RoleActions = {
    canUpdate: boolean;
    canDelete: boolean;
    edit: (role: RoleListItem) => void;
    remove: (role: RoleListItem) => void;
};

export function RolesList() {
    const {t} = useI18n();
    const [page, goToPage] = usePageParam();
    const canCreate = can("roles.create");
    const [formOpen, setFormOpen] = useState(false);
    const [editingRole, setEditingRole] = useState<RoleListItem | null>(null);
    const [deletingRole, setDeletingRole] = useState<RoleListItem | null>(null);

    const {status, data, error, reload} = useRequest(String(page), () => getRolesPage(page), t("roles.loadError"));
    const items = data?.items ?? [];

    const openForm = (role: RoleListItem | null) => {
        setEditingRole(role);
        setFormOpen(true);
    };
    const actions: RoleActions = {
        canUpdate: can("roles.update"),
        canDelete: can("roles.delete"),
        edit: openForm,
        remove: setDeletingRole,
    };
    const showActions = actions.canUpdate || actions.canDelete;

    const createButton = (className?: string) =>
        canCreate ? (
            <Button type="button" className={className} onClick={() => openForm(null)}>
                <Plus aria-hidden/>
                {t("roles.create")}
            </Button>
        ) : null;

    return (
        <div className="stack stack--lg w-full">
            <PageHeader id="roles-heading" title={t("roles.title")} subtitle={t("roles.subtitle")} action={createButton("self-start")}/>

            {status === "error" ? (
                <StatusCard title={t("roles.loadErrorTitle")} detail={error} onRetry={reload} />
            ) : status === "ready" && data?.total === 0 ? (
                <StatusCard title={t("roles.emptyTitle")} detail={t("roles.emptyDescription")}>
                    {createButton()}
                </StatusCard>
            ) : (
                <div className="stack">
                    <DataTable
                        aria-labelledby="roles-heading"
                        columns={[
                            {label: t("common.name"), className: "px-4"},
                            {label: t("common.key")},
                            {label: t("roles.table.permissions")},
                            showActions && {label: t("common.actions"), className: "px-4 text-right"},
                        ]}
                        loading={status === "loading"}
                        loadingText={t("roles.loading")}
                    >
                        {items.map((role) => (
                            <RoleRow key={role.key} role={role} actions={showActions ? actions : null}/>
                        ))}
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

            <RoleFormDialog
                key={editingRole?.key ?? "create"}
                open={formOpen}
                role={editingRole}
                onOpenChange={setFormOpen}
                onSaved={reload}
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
                        refreshAfterDelete(page, items.length, goToPage, reload);
                    }
                }}
            />
        </div>
    );
}

function RoleRow({role, actions}: {role: RoleListItem; actions: RoleActions | null}) {
    const {t} = useI18n();
    const permissionNames = role.permissions.map((permission) => permission.name).join(", ");

    return (
        <TableRow>
            <TableCell className="px-4 font-medium">{role.name}</TableCell>
            <TableCell className="text-muted-foreground">{role.key}</TableCell>
            <TableCell className="max-w-xs truncate" title={permissionNames || undefined}>
                {permissionNames || t("common.noDataDash")}
            </TableCell>
            {actions ? (
                <TableCell className="px-4">
                    <div className="flex justify-end gap-1">
                        {actions.canUpdate ? (
                            <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                aria-label={t("roles.editAria", {name: role.name})}
                                onClick={() => actions.edit(role)}
                            >
                                <Pencil aria-hidden/>
                                {t("common.edit")}
                            </Button>
                        ) : null}
                        {actions.canDelete ? (
                            <Button
                                type="button"
                                variant="destructive"
                                size="sm"
                                // The Admin role cannot be deleted; the label says why.
                                aria-label={
                                    role.protected ? t("roles.cannotDeleteAdmin") : t("roles.deleteAria", {name: role.name})
                                }
                                title={role.protected ? t("roles.cannotDeleteAdmin") : undefined}
                                disabled={role.protected}
                                onClick={() => actions.remove(role)}
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
}
