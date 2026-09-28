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
import {extensions, mergeByKey} from "./extensions";

const pageRoutes: RouteObject[] = [
    {
        index: true,
        Component: Home,
    },
    {
        path: "users",
        Component: UsersList,
    },
    {
        path: "roles",
        Component: RolesList,
    },
    {
        path: "permissions",
        Component: PermissionsList,
    },
    {
        path: "documents",
        Component: Documents,
    },
];

const routeKey = (route: RouteObject) =>
    route.index ? "" : route.path?.replace(/^\/+|\/+$/g, "");

const routes: RouteObject[] = [
    {
        path: "/login",
        Component: Login,
    },
    {
        Component: SessionGate,
        children: [
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
