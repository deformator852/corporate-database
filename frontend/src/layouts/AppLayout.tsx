import {Database, LogOut} from "lucide-react";
import {useState} from "react";
import {Outlet, useLocation} from "react-router";

import {Button} from "@/components/ui/button";
import {useSessionStore} from "@/shared/auth/session-store";
import {signOut} from "@/shared/lib/api/me";
import type {SessionUser} from "@/shared/auth/types";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {ThemeSwitcher} from "@/theme/ThemeSwitcher";
import {NotificationBell} from "@/widgets/notifications/ui/NotificationBell";
import {Sidebar} from "@/widgets/sidebar/ui/Sidebar.tsx";

export default function AppLayout() {
    const {t} = useI18n();
    const user = useSessionStore((state) => state.user);
    const location = useLocation();
    const pane = location.pathname === "/";

    if (!user) {
        return null;
    }

    return (
        <div className="app app-layout">
            <header className="app-header app-layout__header">
                <div className="app-header__inner">
                    <div className="flex min-w-0 items-center gap-2.5">
                        <span
                            className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground"
                            aria-hidden
                        >
                            <Database className="size-4" strokeWidth={2} />
                        </span>
                        <strong className="truncate text-sm font-semibold tracking-tight">
                            {t("app.title")}
                        </strong>
                    </div>
                    <div className="flex shrink-0 items-center gap-0.5">
                        <NotificationBell />
                        <ThemeSwitcher />
                        <span
                            className="mx-1.5 hidden h-4 w-px bg-border sm:block"
                            aria-hidden
                        />
                        <HeaderUser user={user} />
                        <SignOutButton />
                    </div>
                </div>
            </header>

            <div className="app-layout__body">
                <Sidebar />
                <main className="app-main app-layout__main">
                    <div
                        className={
                            pane
                                ? "container app-layout__content app-layout__content--pane"
                                : "container app-layout__content"
                        }
                    >
                        <Outlet />
                    </div>
                </main>
            </div>
        </div>
    );
}

function SignOutButton() {
    const {t} = useI18n();
    const [pending, setPending] = useState(false);

    return (
        <Button
            type="button"
            variant="ghost"
            size="icon"
            className="ml-1"
            aria-label={t("auth.signOut")}
            title={t("auth.signOut")}
            disabled={pending}
            onClick={() => {
                setPending(true);
                // Session state is cleared even if the request fails.
                void signOut().catch(() => undefined);
            }}
        >
            <LogOut />
        </Button>
    );
}

function HeaderUser({user}: {user: SessionUser}) {
    const name = `${user.first_name} ${user.last_name}`.trim();
    const initials = `${user.first_name.charAt(0)}${user.last_name.charAt(0)}`.toUpperCase();

    return (
        <div
            className="flex items-center gap-2 pl-1"
            title={user.email}
        >
            <span
                className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium"
                aria-hidden
            >
                {initials}
            </span>
            <span className="hidden min-w-0 max-w-48 flex-col leading-tight sm:flex">
                <span className="truncate text-sm font-medium">{name}</span>
                <span className="truncate text-xs text-muted-foreground">
                    {user.email}
                </span>
            </span>
            <span className="sr-only sm:hidden">
                {name}, {user.email}
            </span>
        </div>
    );
}
