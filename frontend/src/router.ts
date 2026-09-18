import {createBrowserRouter, type RouteObject} from "react-router";
import Login from "@/pages/login/ui/Login";
import Home from "@/pages/home/ui/Home";
import AppLayout from "./layouts/AppLayout";
import {SessionGate} from "@/shared/auth/SessionGate";

const routes: RouteObject[] = [
    {
        path: "/",
        Component: SessionGate,
        children: [
            {
                path: "login",
                Component: Login,
            },
            {
                Component: AppLayout,
                children: [
                    {
                        index: true,
                        Component: Home,
                    },
                ],
            },
        ],
    },
];

export default createBrowserRouter(routes);
