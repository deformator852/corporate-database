import {createBrowserRouter, type RouteObject} from "react-router";
import Login from "@pages/login/ui/Login";
import Home from "@pages/home/ui/Home";
import NotFound from "@pages/not-found/ui/NotFound";
import AppLayout from "./layouts/AppLayout";
import {SessionGate} from "@/shared/auth/SessionGate";
import {UsersList} from "@pages/users/list/ui/UsersList";
import {RolesList} from "@pages/roles/ui/RolesList";
import {PermissionsList} from "@pages/permissions/ui/PermissionsList";
import {Documents} from "@pages/documents/ui/Documents";
import {AuditLog} from "@pages/audit/ui/AuditLog";
import {UserDetail} from "@pages/users/detail/ui/UserDetail";
import {SystemStatusPage} from "@pages/system/ui/SystemStatusPage";
import {RatedAnswers} from "@pages/feedback/ui/RatedAnswers";
import {Account} from "@pages/account/ui/Account";
import {ChatHistoryList} from "@pages/chat-history/ui/ChatHistoryList";
import {ChatReview} from "@pages/chat-history/ui/ChatReview";
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
    {
        path: "feedback",
        Component: RatedAnswers,
        handle: {can: "chat.feedback"} satisfies RouteHandle,
    },
    {
        // Every signed-in user's own account.
        path: "account",
        Component: Account,
    },
    {
        path: "chat-history",
        Component: ChatHistoryList,
        handle: {can: "chat.history"} satisfies RouteHandle,
    },
    {
        path: "chat-history/:conversationId",
        Component: ChatReview,
        handle: {can: "chat.history"} satisfies RouteHandle,
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
