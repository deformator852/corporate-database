import {createBrowserRouter, type RouteObject} from "react-router";
import Login from "@/pages/login/ui/Login";
import Home from "@/pages/home/ui/Home";
import NotFound from "@/pages/not-found/ui/NotFound";
import AppLayout from "./layouts/AppLayout";
import {SessionGate} from "@/shared/auth/SessionGate";
import {UsersList} from "@pages/users/list/ui/UsersList.tsx";
import {RolesList} from "@pages/roles/list/ui/RolesList";
import {PermissionsList} from "@pages/permissions/list/ui/PermissionsList";
import {Documents} from "@pages/documents/ui/Documents";
import {AuditLog} from "@pages/audit/ui/AuditLog";
import {UserDetail} from "@pages/users/detail/ui/UserDetail";
import {SystemStatusPage} from "@pages/system/ui/SystemStatusPage";
import {extensions, mergeByKey} from "./extensions";

/** `handle.can`: the permission a page needs. Without it the layout shows
 * the not-found page, like the API does for things the user may not see. */
export type RouteHandle = {can?: string};

const pageRoutes: RouteObject[] = [
    {
        index: true,
        Component: Home,
    },
    {
        path: "users",
        Component: UsersList,
        handle: {can: "users.list"} satisfies RouteHandle,
    },
    {
        path: "roles",
        Component: RolesList,
        handle: {can: "roles.list"} satisfies RouteHandle,
    },
    {
        path: "permissions",
        Component: PermissionsList,
        handle: {can: "permissions.list"} satisfies RouteHandle,
    },
    {
        path: "documents",
        Component: Documents,
    },
    {
        path: "audit",
        Component: AuditLog,
        handle: {can: "audit.list"} satisfies RouteHandle,
    },
    {
        path: "users/:userId",
        Component: UserDetail,
        handle: {can: "users.view"} satisfies RouteHandle,
    },
    {
        path: "system",
        Component: SystemStatusPage,
        handle: {can: "system.view"} satisfies RouteHandle,
    },
];

const routeKey = (route: RouteObject) =>
    route.index ? "" : route.path?.replace(/^\/+|\/+$/g, "");

export const routes: RouteObject[] = [
    {
        // SessionGate sends a signed-in user from /login to the app.
        Component: SessionGate,
        children: [
            {
                path: "/login",
                Component: Login,
            },
            {
                Component: AppLayout,
                children: [
                    ...mergeByKey(
                        pageRoutes,
                        extensions.flatMap((extension) => extension.routes ?? []),
                        routeKey,
                    ),
                    {
                        path: "*",
                        Component: NotFound,
                    },
                ],
            },
        ],
    },
];

export default createBrowserRouter(routes);
