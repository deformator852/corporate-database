import {can} from "@/shared/lib/api/me.ts";
import {NavLink} from "react-router";

type NavItem = {
    to: string;
    label: string;
    end?: boolean;
    can?: string;
};

export function Sidebar() {
    const nav = [
        {to: "/", label: "Home", end: true},
        {to: "/documents", label: "Documents", end: true, can: "documents.list"},
        {to: "/users", label: "Users", end: true, can: "users.list"},
        {to: "/roles", label: "Roles", end: true, can: "roles.list"},
        {to: "/permissions", label: "Permissions", end: true, can: "permissions.list"},
    ] satisfies NavItem[];
    return <aside className="app-layout__sidebar" aria-label="Navigation">
        <nav className="app-layout__nav">
            {nav.map((item) => (
                (!item.can || can(item.can)) &&
                (<NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    className={({isActive}) =>
                        `app-layout__nav-link${isActive ? " app-layout__nav-link--active" : ""}`
                    }
                >
                    {item.label}
                </NavLink>)
            ))}
        </nav>
    </aside>
}