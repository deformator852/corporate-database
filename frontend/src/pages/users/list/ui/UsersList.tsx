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
import {useSessionStore} from "@/shared/auth/session-store";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {can} from "@/shared/lib/api/me";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {getUsersPage} from "@pages/users/list/api/users";
import {
    USERS_PER_PAGE,
    type UserListItem,
    type UserListPage,
} from "@pages/users/list/model/users";
import {DeleteUserDialog} from "@pages/users/list/ui/DeleteUserDialog";
import {UserFormDialog} from "@pages/users/list/ui/UserFormDialog";

function fullName(user: UserListItem) {
    return `${user.first_name} ${user.last_name}`;
}

function parsePage(value: string | null): number {
    const page = Number(value);
    if (!Number.isInteger(page) || page < 1) {
        return 1;
    }
    return page;
}

type LoadState =
    | {key: string; status: "ready"; data: UserListPage}
    | {key: string; status: "error"; message: string};

export function UsersList() {
    const {t} = useI18n();
    const [searchParams, setSearchParams] = useSearchParams();
    const page = parsePage(searchParams.get("page"));
    const [reloadKey, setReloadKey] = useState(0);
    const requestKey = `${page}:${reloadKey}`;
    const [load, setLoad] = useState<LoadState | null>(null);

    const canCreate = can("users.create");
    const canUpdate = can("users.update");
    const canDelete = can("users.delete");
    const showActions = canUpdate || canDelete;
    const sessionUser = useSessionStore((state) => state.user);
    const [formOpen, setFormOpen] = useState(false);
    const [editingUser, setEditingUser] = useState<UserListItem | null>(null);
    const [deletingUser, setDeletingUser] = useState<UserListItem | null>(null);

    useEffect(() => {
        let cancelled = false;

        void getUsersPage(page)
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
                        message: getApiErrorMessage(reason, t("users.loadError")),
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
    const perPage = data?.per_page ?? USERS_PER_PAGE;
    const from = total === 0 ? 0 : (page - 1) * perPage + 1;
    const to = total === 0 ? 0 : (page - 1) * perPage + items.length;

    const openCreate = () => {
        setEditingUser(null);
        setFormOpen(true);
    };

    const openEdit = (user: UserListItem) => {
        setEditingUser(user);
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

    const isSelf = (user: UserListItem) => {
        if (sessionUser == null) {
            return false;
        }
        return sessionUser.id === user.id || sessionUser.email === user.email;
    };

    return (
        <div className="stack stack--lg w-full">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="stack">
                    <h1 id="users-heading">{t("users.title")}</h1>
                    <p className="max-w-xl text-muted-foreground">
                        {t("users.subtitle")}
                    </p>
                </div>
                {canCreate ? (
                    <Button type="button" className="self-start" onClick={openCreate}>
                        <Plus aria-hidden/>
                        {t("users.create")}
                    </Button>
                ) : null}
            </div>

            {status === "error" ? (
                <div className="flex flex-col items-start gap-3 rounded-xl bg-card px-4 py-8 ring-1 ring-foreground/10">
                    <p className="font-medium">{t("users.loadErrorTitle")}</p>
                    <p className="text-sm text-muted-foreground">{error}</p>
                    <Button type="button" onClick={() => setReloadKey((key) => key + 1)}>
                        {t("common.tryAgain")}
                    </Button>
                </div>
            ) : status === "ready" && total === 0 ? (
                <div className="flex flex-col items-start gap-3 rounded-xl bg-card px-4 py-8 ring-1 ring-foreground/10">
                    <p className="font-medium">{t("users.emptyTitle")}</p>
                    <p className="text-sm text-muted-foreground">
                        {t("users.emptyDescription")}
                    </p>
                    {canCreate ? (
                        <Button type="button" onClick={openCreate}>
                            <Plus aria-hidden/>
                            {t("users.create")}
                        </Button>
                    ) : null}
                </div>
            ) : (
                <div className="stack">
                    <Card className="gap-0 py-0">
                        <Table aria-labelledby="users-heading">
                            <TableHeader>
                                <TableRow className="hover:bg-transparent">
                                    <TableHead className="px-4">{t("common.name")}</TableHead>
                                    <TableHead>{t("common.email")}</TableHead>
                                    <TableHead>{t("users.table.role")}</TableHead>
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
                                            {t("users.loading")}
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    items.map((user) => (
                                        <TableRow key={user.id}>
                                            <TableCell className="px-4 font-medium">
                                                {fullName(user)}
                                            </TableCell>
                                            <TableCell className="text-muted-foreground">
                                                {user.email}
                                            </TableCell>
                                            <TableCell>
                                                {user.roles.length > 0
                                                    ? user.roles
                                                          .map((role) => role.name)
                                                          .join(", ")
                                                    : t("common.noDataDash")}
                                            </TableCell>
                                            {showActions ? (
                                                <TableCell className="px-4">
                                                    <div className="flex justify-end gap-1">
                                                        {canUpdate ? (
                                                            <Button
                                                                type="button"
                                                                variant="ghost"
                                                                size="sm"
                                                                aria-label={t("users.editAria", {
                                                                    name: fullName(user),
                                                                })}
                                                                onClick={() => openEdit(user)}
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
                                                                    isSelf(user)
                                                                        ? t("users.cannotDeleteSelf")
                                                                        : t("users.deleteAria", {
                                                                              name: fullName(user),
                                                                          })
                                                                }
                                                                disabled={isSelf(user)}
                                                                title={
                                                                    isSelf(user)
                                                                        ? t("users.cannotDeleteSelf")
                                                                        : undefined
                                                                }
                                                                onClick={() => setDeletingUser(user)}
                                                            >
                                                                <Trash2 aria-hidden/>
                                                                {t("common.delete")}
                                                            </Button>
                                                        ) : null}
                                                    </div>
                                                </TableCell>
                                            ) : null}
                                        </TableRow>
                                    ))
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

            <UserFormDialog
                key={editingUser?.id ?? "create"}
                open={formOpen}
                user={editingUser}
                onOpenChange={setFormOpen}
                onSaved={handleSaved}
            />
            <DeleteUserDialog
                user={deletingUser}
                open={deletingUser != null}
                onOpenChange={(open) => {
                    if (!open) {
                        setDeletingUser(null);
                    }
                }}
                onDeleted={handleDeleted}
            />
        </div>
    );
}
