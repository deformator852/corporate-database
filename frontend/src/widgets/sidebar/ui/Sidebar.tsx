import {Menu, X} from "lucide-react";
import {useState} from "react";
import {NavLink} from "react-router";

import {Button} from "@/components/ui/button";
import {Sheet, SheetClose, SheetContent, SheetTitle, SheetTrigger} from "@/components/ui/sheet";
import {extensions, mergeByKey} from "@/extensions";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {can} from "@/shared/lib/api/me.ts";
import {CORE_NAV} from "@/widgets/sidebar/model/nav";

const nav = mergeByKey(
    CORE_NAV,
    extensions.flatMap((extension) => extension.nav ?? []),
    (item) => item.to,
);

/** The links the user may open; the same list on desktop and in the phone menu. */
function NavLinks({className, onNavigate}: {className: string; onNavigate?: () => void}) {
    const {t} = useI18n();
    return (
        <nav className={className}>
            {nav.map((item) =>
                (!item.can || can(item.can)) ? (
                    <NavLink
                        key={item.to}
                        to={item.to}
                        end={item.end}
                        onClick={onNavigate}
                        className={({isActive}) =>
                            `app-layout__nav-link${isActive ? " app-layout__nav-link--active" : ""}`
                        }
                    >
                        {item.icon ? <item.icon className="app-layout__nav-icon" aria-hidden/> : null}
                        {t(item.labelKey)}
                    </NavLink>
                ) : null,
            )}
        </nav>
    );
}

/** Desktop: a column next to the page. Hidden on phones (see MobileNav). */
export function Sidebar() {
    const {t} = useI18n();
    return (
        <aside className="app-layout__sidebar" aria-label={t("nav.label")}>
            <NavLinks className="app-layout__nav"/>
        </aside>
    );
}

/** Phones: a menu button in the header that slides the links in from the left. */
export function MobileNav() {
    const {t} = useI18n();
    const [open, setOpen] = useState(false);
    return (
        <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger
                render={
                    <Button type="button" variant="ghost" size="icon" className="-ms-2 md:hidden" aria-label={t("nav.openMenu")}/>
                }
            >
                <Menu aria-hidden/>
            </SheetTrigger>
            <SheetContent side="left" showCloseButton={false} className="gap-0 bg-sidebar p-0">
                <div className="flex min-h-[var(--header-height)] items-center justify-between border-b px-4">
                    <SheetTitle>{t("nav.label")}</SheetTitle>
                    <SheetClose render={<Button type="button" variant="ghost" size="icon" aria-label={t("common.close")}/>}>
                        <X aria-hidden/>
                    </SheetClose>
                </div>
                <NavLinks className="flex flex-col gap-1 p-3" onNavigate={() => setOpen(false)}/>
            </SheetContent>
        </Sheet>
    );
}
