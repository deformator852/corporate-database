import {LogOut} from "lucide-react";
import {useState} from "react";
import {Link, Outlet, useLocation, useMatches} from "react-router";

import {Button} from "@/components/ui/button";
import {useSessionStore} from "@/shared/auth/session-store";
import {can, signOut} from "@/shared/lib/api/me";
import NotFound from "@pages/not-found/ui/NotFound";
import type {RouteHandle} from "@/router";
import {Logo} from "@/shared/ui/Logo";
import type {SessionUser} from "@/shared/auth/types";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {ThemeSwitcher} from "@/theme/ThemeSwitcher";
import {LanguageSwitcher} from "@/widgets/language-switcher/ui/LanguageSwitcher";
import {NotificationBell} from "@/widgets/notifications/ui/NotificationBell";
import {ReindexBanner} from "@/widgets/reindex-banner/ui/ReindexBanner";
import {MobileNav, Sidebar} from "@/widgets/sidebar/ui/Sidebar";

export default function AppLayout() {
    const user = useSessionStore((state) => state.user);
    const location = useLocation();
    const pane = location.pathname === "/";
    const allowed = useMatches().every((match) => {
        const permission = (match.handle as RouteHandle | undefined)?.can;
        return !permission || can(permission, user);
    });

    if (!user) {
        return null;
    }

    return (
        <div className="app app-layout">
            <header className="d-navbar sticky top-0 z-50 min-h-(--header-height) shrink-0 justify-between gap-(--stack-gap) border-b border-base-300 bg-base-100/90 px-(--gutter) py-0 backdrop-blur-sm">
                <div className="flex min-w-0 items-center gap-1">
                    <MobileNav />
                    <Link to="/" className="min-w-0 rounded-md outline-none focus-visible:ring-3 focus-visible:ring-primary/50">
                    <Logo />
                    </Link>
                </div>
                <div className="flex shrink-0 items-center gap-0.5">
                    <NotificationBell />
                    <LanguageSwitcher />
                    <ThemeSwitcher />
                    <span
                        className="mx-1.5 hidden h-4 w-px bg-base-300 sm:block"
                        aria-hidden
                    />
                    <HeaderUser user={user} />
                    <SignOutButton />
                </div>
            </header>

            <div className="app-layout__body">
                <Sidebar />
                <main className="app-main app-layout__main">
                    <ReindexBanner />
                    <div
                        className={
                            pane
                                ? "container app-layout__content app-layout__content--pane"
                                : "container app-layout__content"
                        }
                    >
                        {allowed ? <Outlet /> : <NotFound />}
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
    const {t} = useI18n();
    const name = `${user.first_name} ${user.last_name}`.trim();
    const initials = `${user.first_name.charAt(0)}${user.last_name.charAt(0)}`.toUpperCase();

    return (
        <Link
            to="/account"
            className="flex items-center gap-2 rounded-md pl-1 outline-none hover:bg-base-200 focus-visible:ring-3 focus-visible:ring-primary/50"
            title={t("account.title")}
        >
            <div className="d-avatar d-avatar-placeholder shrink-0" aria-hidden>
                <div className="size-8 rounded-full bg-base-200 text-xs font-medium">{initials}</div>
            </div>
            <span className="hidden min-w-0 max-w-48 flex-col leading-tight sm:flex">
                <span className="truncate text-sm font-medium">{name}</span>
                <span className="truncate text-xs text-base-content/70">
                    {user.email}
                </span>
            </span>
            <span className="sr-only sm:hidden">
                {name}, {user.email}
            </span>
        </Link>
    );
}
