import {KeyRound} from "lucide-react";

import {buttonVariants} from "@/components/ui/button";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {SSO_START_URL} from "@pages/login/api/login";

/** "Sign in with …": a link, so the browser itself goes to the company's
 * sign-in page. */
export function SsoSignIn({name}: {name: string}) {
    const {t} = useI18n();
    return (
        <a href={SSO_START_URL} className={buttonVariants({size: "lg", className: "w-full"})}>
            <KeyRound aria-hidden />
            {t("login.sso.button", {name})}
        </a>
    );
}
