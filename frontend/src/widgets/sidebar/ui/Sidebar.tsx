import {Menu, X} from "lucide-react";
import {useState} from "react";
import {NavLink} from "react-router";

import {Button} from "@/components/ui/button";
import {Sheet, SheetClose, SheetContent, SheetTitle, SheetTrigger} from "@/components/ui/sheet";
import {extensions, mergeByKey} from "@/extensions";
import {useSessionStore} from "@/shared/auth/session-store";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {can} from "@/shared/lib/api/me.ts";
import {CORE_NAV} from "@/widgets/sidebar/model/nav";

const nav = mergeByKey(
    CORE_NAV,
    extensions.flatMap((extension) => extension.nav ?? []),
    (item) => item.to,
);

/** The links the user may open; the same list on desktop and in the phone menu. */
function NavLinks({className, onNavigate}: {className?: string; onNavigate?: () => void}) {
    const {t} = useI18n();
    return (
        <nav className={className}>
            <ul className="d-menu w-full flex-nowrap gap-0.5 p-0">
                {nav.map((item) =>
                    (!item.can || can(item.can)) ? (
                        <li key={item.to}>
                            <NavLink
                                to={item.to}
                                end={item.end}
                                onClick={onNavigate}
                                className={({isActive}) => (isActive ? "bg-primary font-medium text-primary-content" : "font-medium")}
                            >
                                {item.icon ? <item.icon className="size-4" aria-hidden/> : null}
                                {t(item.labelKey)}
                            </NavLink>
                        </li>
                    ) : null,
                )}
            </ul>
        </nav>
    );
}

/** "Built with Llama", as the Llama license asks of products built with it.
 * Its exact wording: not translated. */
function ModelNotice({className}: {className: string}) {
    const builtWithLlama = useSessionStore((state) => state.user?.built_with_llama);
    return builtWithLlama ? <p className={`text-xs text-base-content/70 ${className}`}>Built with Llama</p> : null;
}

/** Desktop: a column next to the page. Hidden on phones (see MobileNav). */
export function Sidebar() {
    const {t} = useI18n();
    return (
        <aside className="app-layout__sidebar" aria-label={t("nav.label")}>
            <NavLinks/>
            <ModelNotice className="mt-auto px-3 pt-4"/>
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
            <SheetContent side="left" showCloseButton={false} className="gap-0 bg-base-100 p-0">
                <div className="flex min-h-[var(--header-height)] items-center justify-between border-b px-4">
                    <SheetTitle>{t("nav.label")}</SheetTitle>
                    <SheetClose render={<Button type="button" variant="ghost" size="icon" aria-label={t("common.close")}/>}>
                        <X aria-hidden/>
                    </SheetClose>
                </div>
                <NavLinks className="p-3" onNavigate={() => setOpen(false)}/>
                <ModelNotice className="mt-auto p-4"/>
            </SheetContent>
        </Sheet>
    );
}
