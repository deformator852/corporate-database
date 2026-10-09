import {useState} from "react";
import {Ban, CircleCheck, Pencil, Plus, Trash2} from "lucide-react";
import {Link, useLocation} from "react-router";

import {Badge} from "@/components/ui/badge";
import {Button} from "@/components/ui/button";
import {TableCell, TableRow} from "@/components/ui/table";
import type {UserDetailLinkState} from "@/entities/user/model";
import {useSessionStore} from "@/shared/auth/session-store";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {can} from "@/shared/lib/api/me";
import {refreshAfterDelete, usePageParam} from "@/shared/lib/hooks/usePageParam";
import {useRequest} from "@/shared/lib/hooks/useRequest";
import {ConfirmDialog} from "@/shared/ui/ConfirmDialog";
import {DataTable} from "@/shared/ui/DataTable";
import {ListPagination} from "@/shared/ui/ListPagination";
import {PageHeader} from "@/shared/ui/PageHeader";
import {StatusCard} from "@/shared/ui/StatusCard";
import {deleteUser, disableUser, enableUser, getUsersPage} from "@pages/users/list/api/users";
import type {UserListItem} from "@pages/users/list/model/users";
import {UserFormDialog} from "@pages/users/list/ui/UserFormDialog";

function fullName(user: UserListItem) {
    return `${user.first_name} ${user.last_name}`;
}

/** What the signed-in user may do to the users in the list. */
type UserActions = {
    canUpdate: boolean;
    canDisable: boolean;
    canDelete: boolean;
    edit: (user: UserListItem) => void;
    enable: (user: UserListItem) => void;
    disable: (user: UserListItem) => void;
    remove: (user: UserListItem) => void;
    enablingId: number | null;
    // Shown in the row whose "Enable" failed.
    enableError: {id: number; message: string} | null;
    isSelf: (user: UserListItem) => boolean;
};

export function UsersList() {
    const {t} = useI18n();
    const [page, goToPage] = usePageParam();
    const sessionUser = useSessionStore((state) => state.user);
    const canCreate = can("users.create");
    const [formOpen, setFormOpen] = useState(false);
    const [editingUser, setEditingUser] = useState<UserListItem | null>(null);
    const [deletingUser, setDeletingUser] = useState<UserListItem | null>(null);
    const [disablingUser, setDisablingUser] = useState<UserListItem | null>(null);
    const [enablingId, setEnablingId] = useState<number | null>(null);
    const [enableError, setEnableError] = useState<UserActions["enableError"]>(null);

    const {status, data, error, reload} = useRequest(String(page), () => getUsersPage(page), t("users.loadError"));
    const items = data?.items ?? [];

    const openForm = (user: UserListItem | null) => {
        setEditingUser(user);
        setFormOpen(true);
    };

    const enable = async (user: UserListItem) => {
        setEnablingId(user.id);
        setEnableError(null);
        try {
            await enableUser(user.id);
            reload();
        } catch (reason) {
            setEnableError({id: user.id, message: getApiErrorMessage(reason, t("users.enableError"))});
        } finally {
            setEnablingId(null);
        }
    };

    const actions: UserActions = {
        canUpdate: can("users.update"),
        canDisable: can("users.disable"),
        canDelete: can("users.delete"),
        edit: openForm,
        enable: (user) => void enable(user),
        disable: setDisablingUser,
        remove: setDeletingUser,
        enablingId,
        enableError,
        isSelf: (user) => sessionUser != null && (sessionUser.id === user.id || sessionUser.email === user.email),
    };
    const showActions = actions.canUpdate || actions.canDisable || actions.canDelete;

    const createButton = (className?: string) =>
        canCreate ? (
            <Button type="button" className={className} onClick={() => openForm(null)}>
                <Plus aria-hidden/>
                {t("users.create")}
            </Button>
        ) : null;

    return (
        <div className="stack stack--lg w-full">
            <PageHeader id="users-heading" title={t("users.title")} subtitle={t("users.subtitle")} action={createButton("self-start")}/>

            {status === "error" ? (
                <StatusCard title={t("users.loadErrorTitle")} detail={error} onRetry={reload} />
            ) : status === "ready" && data?.total === 0 ? (
                <StatusCard title={t("users.emptyTitle")} detail={t("users.emptyDescription")}>
                    {createButton()}
                </StatusCard>
            ) : (
                <div className="stack">
                    <DataTable
                        aria-labelledby="users-heading"
                        columns={[
                            {label: t("common.name"), className: "px-4"},
                            {label: t("common.email")},
                            {label: t("users.table.role")},
                            showActions && {label: t("common.actions"), className: "px-4 text-right"},
                        ]}
                        loading={status === "loading"}
                        loadingText={t("users.loading")}
                    >
                        {items.map((user) => (
                            <UserRow key={user.id} user={user} actions={showActions ? actions : null}/>
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

            <UserFormDialog
                key={editingUser?.id ?? "create"}
                open={formOpen}
                user={editingUser}
                onOpenChange={setFormOpen}
                onSaved={reload}
            />
            <ConfirmDialog
                open={deletingUser != null}
                onOpenChange={(open) => {
                    if (!open) {
                        setDeletingUser(null);
                    }
                }}
                title={t("users.delete.title", {
                    name: deletingUser ? fullName(deletingUser) : t("common.thisUser"),
                })}
                description={t("users.delete.description")}
                confirmLabel={t("users.delete.confirm")}
                pendingLabel={t("common.deleting")}
                errorMessage={t("users.delete.error")}
                onConfirm={async () => {
                    if (deletingUser) {
                        await deleteUser(deletingUser.id);
                        refreshAfterDelete(page, items.length, goToPage, reload);
                    }
                }}
            />
            <ConfirmDialog
                open={disablingUser != null}
                onOpenChange={(open) => {
                    if (!open) {
                        setDisablingUser(null);
                    }
                }}
                title={t("users.disableDialog.title", {
                    name: disablingUser ? fullName(disablingUser) : t("common.thisUser"),
                })}
                description={t("users.disableDialog.description")}
                confirmLabel={t("users.disableDialog.confirm")}
                pendingLabel={t("common.disabling")}
                errorMessage={t("users.disableDialog.error")}
                onConfirm={async () => {
                    if (disablingUser) {
                        await disableUser(disablingUser.id);
                        reload();
                    }
                }}
            />
        </div>
    );
}

function UserRow({user, actions}: {user: UserListItem; actions: UserActions | null}) {
    const {t} = useI18n();
    const location = useLocation();
    // The user page's Back link returns to this page of the list.
    const linkState: UserDetailLinkState = {from: location.pathname + location.search};
    const name = fullName(user);

    return (
        <TableRow>
            <TableCell className="px-4 font-medium">
                <span className="inline-flex flex-wrap items-center gap-2">
                    {can("users.view") ? (
                        <Link
                            to={`/users/${user.id}`}
                            state={linkState}
                            className="underline-offset-4 hover:underline"
                            aria-label={t("userDetail.openAria", {name})}
                        >
                            {name}
                        </Link>
                    ) : (
                        name
                    )}
                    {user.disabled ? <Badge variant="secondary">{t("users.disabled")}</Badge> : null}
                </span>
            </TableCell>
            <TableCell className="text-muted-foreground">{user.email}</TableCell>
            <TableCell>
                {user.roles.length > 0 ? user.roles.map((role) => role.name).join(", ") : t("common.noDataDash")}
            </TableCell>
            {actions ? (
                <TableCell className="px-4">
                    <UserRowActions user={user} actions={actions}/>
                </TableCell>
            ) : null}
        </TableRow>
    );
}

function UserRowActions({user, actions}: {user: UserListItem; actions: UserActions}) {
    const {t} = useI18n();
    const name = fullName(user);
    const self = actions.isSelf(user);

    return (
        <>
            <div className="flex justify-end gap-1">
                {actions.canUpdate ? (
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        aria-label={t("users.editAria", {name})}
                        onClick={() => actions.edit(user)}
                    >
                        <Pencil aria-hidden/>
                        {t("common.edit")}
                    </Button>
                ) : null}
                {actions.canDisable && user.disabled ? (
                    <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        aria-label={t("users.enableAria", {name})}
                        disabled={actions.enablingId === user.id}
                        onClick={() => actions.enable(user)}
                    >
                        <CircleCheck aria-hidden/>
                        {t("users.enable")}
                    </Button>
                ) : null}
                {actions.canDisable && !user.disabled ? (
                    <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        // Nobody can disable or delete themselves; the label says why.
                        aria-label={self ? t("users.cannotDisableSelf") : t("users.disableAria", {name})}
                        title={self ? t("users.cannotDisableSelf") : undefined}
                        disabled={self}
                        onClick={() => actions.disable(user)}
                    >
                        <Ban aria-hidden/>
                        {t("users.disable")}
                    </Button>
                ) : null}
                {actions.canDelete ? (
                    <Button
                        type="button"
                        variant="destructive"
                        size="sm"
                        aria-label={self ? t("users.cannotDeleteSelf") : t("users.deleteAria", {name})}
                        title={self ? t("users.cannotDeleteSelf") : undefined}
                        disabled={self}
                        onClick={() => actions.remove(user)}
                    >
                        <Trash2 aria-hidden/>
                        {t("common.delete")}
                    </Button>
                ) : null}
            </div>
            {actions.enableError?.id === user.id ? (
                <p role="alert" className="mt-1 text-right text-xs text-destructive">
                    {actions.enableError.message}
                </p>
            ) : null}
        </>
    );
}
