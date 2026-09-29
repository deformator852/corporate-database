import {ShieldCheck} from "lucide-react";

import {Card, CardContent, CardDescription, CardHeader, CardTitle} from "@/components/ui/card";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {LogoMark} from "@/shared/ui/Logo";
import {ThemeSwitcher} from "@/theme/ThemeSwitcher";
import {LoginForm} from "@pages/login/ui/LoginForm.tsx";

export default function Login() {
    const {t} = useI18n();
    const app = t("app.title");
    return (
        <div className="relative flex min-h-svh flex-col items-center justify-center bg-muted/40 px-4 py-10">
            <div className="absolute top-4 right-4">
                <ThemeSwitcher />
            </div>

            <main className="flex w-full max-w-sm flex-col items-center">
                <div className="mb-7 flex flex-col items-center gap-3 text-center">
                    <LogoMark className="size-12 shadow-sm" />
                    <div className="space-y-0.5">
                        <p className="text-xl font-semibold tracking-tight">{app}</p>
                        <p className="text-sm text-muted-foreground">{t("app.tagline")}</p>
                    </div>
                </div>

                <Card className="w-full gap-0 py-0 shadow-sm">
                    <CardHeader className="gap-1 px-6 pt-6 pb-0">
                        <CardTitle>
                            <h1 className="text-lg">{t("login.title", {app})}</h1>
                        </CardTitle>
                        <CardDescription>{t("login.description")}</CardDescription>
                    </CardHeader>
                    <CardContent className="px-6 pt-5 pb-6">
                        <LoginForm />
                    </CardContent>
                </Card>

                <p className="mt-6 flex items-center gap-1.5 text-xs text-muted-foreground">
                    <ShieldCheck className="size-3.5" aria-hidden />
                    {t("login.auditNote")}
                </p>
            </main>
        </div>
    );
}
