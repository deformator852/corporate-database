import { NavLink, Outlet } from "react-router";
import { ThemeSwitcher } from "@/theme/ThemeSwitcher";

const nav = [
  { to: "/", label: "Home", end: true },
  { to: "/login", label: "Sign in" },
] as const;

export default function AppLayout() {
  return (
    <div className="app app-layout">
      <header className="app-header app-layout__header">
        <div className="app-header__inner app-layout__header-inner">
          <strong className="app-layout__brand">Corporate Database</strong>
          <ThemeSwitcher />
        </div>
      </header>

      <div className="app-layout__body">
        <aside className="app-layout__sidebar" aria-label="Navigation">
          <nav className="app-layout__nav">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={"end" in item ? item.end : false}
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
