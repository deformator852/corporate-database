import {useEffect, useState} from "react";
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
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {getPermissionsPage} from "@pages/permissions/list/api/permissions";
import {
    PERMISSIONS_PER_PAGE,
    type PermissionListPage,
} from "@pages/permissions/list/model/permissions";

function parsePage(value: string | null): number {
    const page = Number(value);
    if (!Number.isInteger(page) || page < 1) {
        return 1;
    }
    return page;
}

type LoadState =
    | {key: string; status: "ready"; data: PermissionListPage}
    | {key: string; status: "error"; message: string};

export function PermissionsList() {
    const [searchParams, setSearchParams] = useSearchParams();
    const page = parsePage(searchParams.get("page"));
    const [reloadKey, setReloadKey] = useState(0);
    const requestKey = `${page}:${reloadKey}`;
    const [load, setLoad] = useState<LoadState | null>(null);

    useEffect(() => {
        let cancelled = false;

        void getPermissionsPage(page)
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
                        message: getApiErrorMessage(
                            reason,
                            "Could not load permissions.",
                        ),
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
    const perPage = data?.per_page ?? PERMISSIONS_PER_PAGE;
    const from = total === 0 ? 0 : (page - 1) * perPage + 1;
    const to = total === 0 ? 0 : (page - 1) * perPage + items.length;

    return (
        <div className="stack stack--lg w-full">
            <div className="stack">
                <h1 id="permissions-heading">Permissions</h1>
                <p className="max-w-xl text-muted-foreground">
                    Application actions. Assign them to roles when needed.
                </p>
            </div>

            {status === "error" ? (
                <div className="flex flex-col items-start gap-3 rounded-xl bg-card px-4 py-8 ring-1 ring-foreground/10">
                    <p className="font-medium">Could not load permissions</p>
                    <p className="text-sm text-muted-foreground">{error}</p>
                    <Button type="button" onClick={() => setReloadKey((key) => key + 1)}>
                        Try again
                    </Button>
                </div>
            ) : status === "ready" && total === 0 ? (
                <div className="flex flex-col items-start gap-3 rounded-xl bg-card px-4 py-8 ring-1 ring-foreground/10">
                    <p className="font-medium">No permissions yet</p>
                    <p className="text-sm text-muted-foreground">
                        Permissions are defined by the application.
                    </p>
                </div>
            ) : (
                <div className="stack">
                    <Card className="gap-0 py-0">
                        <Table aria-labelledby="permissions-heading">
                            <TableHeader>
                                <TableRow className="hover:bg-transparent">
                                    <TableHead className="px-4">Name</TableHead>
                                    <TableHead>Key</TableHead>
                                    <TableHead className="px-4">Roles</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {status === "loading" ? (
                                    <TableRow className="hover:bg-transparent">
                                        <TableCell
                                            colSpan={3}
                                            className="px-4 py-8 text-muted-foreground"
                                        >
                                            Loading permissions…
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
                                                    {roleNames || "—"}
                                                </TableCell>
                                            </TableRow>
                                        );
                                    })
                                )}
                            </TableBody>
                        </Table>
                    </Card>

                    {status === "ready" ? (
                        <nav
                            aria-label="Pagination"
                            className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
                        >
                            <p className="text-sm text-muted-foreground">
                                Showing {from}–{to} of {total}
                            </p>
                            <div className="flex items-center gap-2">
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    disabled={page <= 1}
                                    onClick={() => goToPage(page - 1)}
                                >
                                    Previous
                                </Button>
                                <p className="min-w-24 text-center text-sm text-muted-foreground">
                                    Page {page} of {Math.max(pages, 1)}
                                </p>
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    disabled={pages === 0 || page >= pages}
                                    onClick={() => goToPage(page + 1)}
                                >
                                    Next
                                </Button>
                            </div>
                        </nav>
                    ) : null}
                </div>
            )}
        </div>
    );
}
