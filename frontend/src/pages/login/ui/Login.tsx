import {CircleAlert, ShieldCheck} from "lucide-react";
import {useEffect, useState} from "react";
import {useSearchParams} from "react-router";

import {Card, CardContent, CardDescription, CardHeader, CardTitle} from "@/components/ui/card";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {LogoMark} from "@/shared/ui/Logo";
import {ThemeSwitcher} from "@/theme/ThemeSwitcher";
import type {MessageKey} from "@/shared/i18n/messages";
import {getSignInMethods, type SignInMethods} from "@pages/login/api/login";
import {LoginForm} from "@pages/login/ui/LoginForm";
import {Button} from "@/components/ui/button";
import {SsoSignIn} from "@pages/login/ui/SsoSignIn";

// Codes the server sends back after a failed SSO sign-in (/login?sso_error=).
const SSO_ERRORS = ["invalid", "sso_denied", "sso_account_exists", "account_disabled", "unavailable"];

// If the server cannot say: the password form, as before.
const FALLBACK: SignInMethods = {password: true, sso: null};

export default function Login() {
    const {t} = useI18n();
    const app = t("app.title");
    const [params] = useSearchParams();
    const ssoError = params.get("sso_error");
    const [methods, setMethods] = useState<SignInMethods | null>(null);
    // With SSO on, administrators still sign in with a password, behind a link.
    const [adminForm, setAdminForm] = useState(false);

    useEffect(() => {
        let current = true;
        getSignInMethods()
            .then((next) => current && setMethods(next))
            .catch(() => current && setMethods(FALLBACK));
        return () => {
            current = false;
        };
    }, []);

    const sso = methods?.sso ?? null;
    // Nothing until the server answers: with SSO on, a password form shown
    // for a moment would invite a sign-in that cannot work.
    const showForm = (methods?.password ?? false) || adminForm;
    return (
        <div className="relative flex min-h-svh flex-col items-center justify-center bg-base-200/40 px-4 py-10">
            <div className="absolute top-4 right-4">
                <ThemeSwitcher />
            </div>

            <main className="flex w-full max-w-sm flex-col items-center">
                <div className="mb-7 flex flex-col items-center gap-3 text-center">
                    <LogoMark className="size-12 shadow-sm" />
                    <div className="space-y-0.5">
                        <p className="text-xl font-semibold tracking-tight">{app}</p>
                        <p className="text-sm text-base-content/70">{t("app.tagline")}</p>
                    </div>
                </div>

                <Card className="w-full gap-0 py-0 shadow-sm">
                    <CardHeader className="gap-1 px-6 pt-6 pb-0">
                        <CardTitle>
                            <h1 className="text-lg">{t("login.title", {app})}</h1>
                        </CardTitle>
                        <CardDescription>{sso ? t("login.sso.description", {name: sso.name}) : t("login.description")}</CardDescription>
                    </CardHeader>
                    <CardContent className="flex flex-col gap-4 px-6 pt-5 pb-6">
                        {ssoError ? (
                            <div
                                role="alert"
                                className="d-alert d-alert-error d-alert-soft items-start text-sm"
                            >
                                <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
                                <p>
                                    {SSO_ERRORS.includes(ssoError)
                                        ? t(`login.sso.error.${ssoError}` as MessageKey)
                                        : t("login.sso.error.other")}
                                </p>
                            </div>
                        ) : null}
                        {sso ? <SsoSignIn name={sso.name} /> : null}
                        {showForm ? <LoginForm /> : null}
                        {sso && !showForm ? (
                            <Button
                                type="button"
                                variant="link"
                                size="sm"
                                className="self-center text-base-content/70"
                                onClick={() => setAdminForm(true)}
                            >
                                {t("login.adminSignIn")}
                            </Button>
                        ) : null}
                    </CardContent>
                </Card>

                <p className="mt-6 flex items-center gap-1.5 text-xs text-base-content/70">
                    <ShieldCheck className="size-3.5" aria-hidden />
                    {t("login.auditNote")}
                </p>
            </main>
        </div>
    );
}
