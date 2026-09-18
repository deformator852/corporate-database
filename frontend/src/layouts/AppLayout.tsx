import {NavLink, Outlet} from "react-router";
import {ThemeSwitcher} from "@/theme/ThemeSwitcher";
import {useSessionStore} from "@/shared/auth/session-store";

const nav = [{to: "/", label: "Home", end: true}] as const;

export default function AppLayout() {
    const user = useSessionStore((state) => state.user);

    if (!user) {
        return null;
    }

    return (
    <div className="app app-layout">
      <header className="app-header app-layout__header">
        <div className="app-header__inner app-layout__header-inner">
          <strong className="app-layout__brand">Corporate Database</strong>
          <div className="flex items-center gap-3">
            <p className="text-sm text-muted-foreground">{user.email}</p>
            <ThemeSwitcher />
          </div>
        </div>
      </header>

      <div className="app-layout__body">
        <aside className="app-layout__sidebar" aria-label="Navigation">
          <nav className="app-layout__nav">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `app-layout__nav-link${isActive ? " app-layout__nav-link--active" : ""}`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </aside>

        <main className="app-main app-layout__main">
          <div className="container app-layout__content">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
