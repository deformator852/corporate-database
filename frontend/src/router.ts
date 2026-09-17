import { createBrowserRouter, type RouteObject } from "react-router";
import Login from "@/pages/login/ui/Login";
import Home from "@/pages/home/ui/Home";
import AppLayout from "./layouts/AppLayout";

const routes: RouteObject[] = [
  {
    path: "/login",
    Component: Login,
  },
  {
    path: "/",
    Component: AppLayout,
    children: [
      {
        index: true,
        Component: Home,
      },
    ],
  },
];

export default createBrowserRouter(routes);
