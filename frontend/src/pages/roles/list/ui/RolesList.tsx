import {useEffect, useState} from "react";
import {Pencil, Plus, Trash2} from "lucide-react";
import {useSearchParams} from "react-router";

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
import {can} from "@/shared/lib/api/me";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {getRolesPage} from "@pages/roles/list/api/roles";
import {
    ROLES_PER_PAGE,
    type RoleListItem,
    type RoleListPage,
} from "@pages/roles/list/model/roles";
import {DeleteRoleDialog} from "@pages/roles/list/ui/DeleteRoleDialog";
import {RoleFormDialog} from "@pages/roles/list/ui/RoleFormDialog";

function parsePage(value: string | null): number {
    const page = Number(value);
    if (!Number.isInteger(page) || page < 1) {
        return 1;
    }
    return page;
}

type LoadState =
    | {key: string; status: "ready"; data: RoleListPage}
    | {key: string; status: "error"; message: string};

export function RolesList() {
    const {t} = useI18n();
    const [searchParams, setSearchParams] = useSearchParams();
    const page = parsePage(searchParams.get("page"));
    const [reloadKey, setReloadKey] = useState(0);
    const requestKey = `${page}:${reloadKey}`;
    const [load, setLoad] = useState<LoadState | null>(null);

    const canCreate = can("roles.create");
    const canUpdate = can("roles.update");
    const canDelete = can("roles.delete");
    const showActions = canUpdate || canDelete;
    const [formOpen, setFormOpen] = useState(false);
    const [editingRole, setEditingRole] = useState<RoleListItem | null>(null);
    const [deletingRole, setDeletingRole] = useState<RoleListItem | null>(null);

    useEffect(() => {
        let cancelled = false;

        void getRolesPage(page)
            .then((data) => {
                if (!cancelled) {
                    setLoad({key: requestKey, status: "ready", data});
                }
            })
            .catch((reason) => {
                if (!cancelled) {
                    setLoad({
                        key: requestKey,
                        status: "error",
                        message: getApiErrorMessage(reason, t("roles.loadError")),
                    });
                }
            });

        return () => {
            cancelled = true;
        };
    }, [page, reloadKey, requestKey]);

    const goToPage = (nextPage: number) => {
        setSearchParams((current) => {
            const params = new URLSearchParams(current);
            if (nextPage <= 1) {
                params.delete("page");
            } else {
                params.set("page", String(nextPage));
            }
            return params;
        });
    };

    const isCurrent = load?.key === requestKey;
    const status = !isCurrent ? "loading" : load.status;
    const data = isCurrent && load.status === "ready" ? load.data : null;
    const error = isCurrent && load.status === "error" ? load.message : null;
    const items = data?.items ?? [];
    const total = data?.total ?? 0;
    const pages = data?.pages ?? 0;
    const perPage = data?.per_page ?? ROLES_PER_PAGE;
    const from = total === 0 ? 0 : (page - 1) * perPage + 1;
    const to = total === 0 ? 0 : (page - 1) * perPage + items.length;

    const openCreate = () => {
        setEditingRole(null);
        setFormOpen(true);
    };

    const openEdit = (role: RoleListItem) => {
        setEditingRole(role);
        setFormOpen(true);
    };

    const handleSaved = () => {
        setReloadKey((key) => key + 1);
    };

    const handleDeleted = () => {
        if (items.length === 1 && page > 1) {
            goToPage(page - 1);
            return;
        }
        setReloadKey((key) => key + 1);
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
                <div className="flex flex-col items-start gap-3 rounded-xl bg-card px-4 py-8 ring-1 ring-foreground/10">
                    <p className="font-medium">{t("roles.loadErrorTitle")}</p>
                    <p className="text-sm text-muted-foreground">{error}</p>
                    <Button type="button" onClick={() => setReloadKey((key) => key + 1)}>
                        {t("common.tryAgain")}
                    </Button>
                </div>
            ) : status === "ready" && total === 0 ? (
                <div className="flex flex-col items-start gap-3 rounded-xl bg-card px-4 py-8 ring-1 ring-foreground/10">
                    <p className="font-medium">{t("roles.emptyTitle")}</p>
                    <p className="text-sm text-muted-foreground">
                        {t("roles.emptyDescription")}
                    </p>
                    {canCreate ? (
                        <Button type="button" onClick={openCreate}>
                            <Plus aria-hidden/>
                            {t("roles.create")}
                        </Button>
                    ) : null}
                </div>
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

                    {status === "ready" ? (
                        <nav
                            aria-label={t("common.pagination")}
                            className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
                        >
                            <p className="text-sm text-muted-foreground">
                                {t("common.showing", {from, to, total})}
                            </p>
                            <div className="flex items-center gap-2">
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    disabled={page <= 1}
                                    onClick={() => goToPage(page - 1)}
                                >
                                    {t("common.previous")}
                                </Button>
                                <p className="min-w-24 text-center text-sm text-muted-foreground">
                                    {t("common.pageOf", {
                                        page,
                                        pages: Math.max(pages, 1),
                                    })}
                                </p>
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    disabled={pages === 0 || page >= pages}
                                    onClick={() => goToPage(page + 1)}
                                >
                                    {t("common.next")}
                                </Button>
                            </div>
                        </nav>
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
            <DeleteRoleDialog
                role={deletingRole}
                open={deletingRole != null}
                onOpenChange={(open) => {
                    if (!open) {
                        setDeletingRole(null);
                    }
                }}
                onDeleted={handleDeleted}
            />
        </div>
    );
}
