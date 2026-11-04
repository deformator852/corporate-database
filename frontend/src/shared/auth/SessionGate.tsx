import {useEffect, useEffectEvent, useState} from "react";
import {Navigate, Outlet, useLocation} from "react-router";

import {Button} from "@/components/ui/button";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {useSessionStore} from "@/shared/auth/session-store";
import {getMe} from "@/shared/lib/api/me";
import {getApiErrorMessage, isUnauthorized} from "@/shared/lib/api/errors";

export function SessionGate() {
    const {t} = useI18n();
    const status = useSessionStore((state) => state.status);
    const user = useSessionStore((state) => state.user);
    const error = useSessionStore((state) => state.error);
    const location = useLocation();
    const [attempt, setAttempt] = useState(0);

    const failed = useEffectEvent((reason: unknown) => getApiErrorMessage(reason, t("session.errorDefault")));

    useEffect(() => {
        const {status: current, setUser, clear, fail} = useSessionStore.getState();
        if (attempt === 0 && current === "ready") {
            return;
        }

        useSessionStore.setState({status: "loading", error: null});

        let cancelled = false;
        void getMe()
            .then((nextUser) => {
                if (!cancelled) {
                    setUser(nextUser);
                }
            })
            .catch((reason) => {
                if (cancelled) {
                    return;
                }
                if (isUnauthorized(reason)) {
                    clear();
                    return;
                }
                fail(failed(reason));
            });

        return () => {
            cancelled = true;
        };
    }, [attempt]);

    if (status === "error") {
        return (
            <div className="flex min-h-svh flex-col items-center justify-center gap-3 px-4">
                <p className="font-medium">{t("session.errorTitle")}</p>
                <p className="text-center text-sm text-base-content/70">
                    {error ?? t("session.errorDefault")}
                </p>
                <Button type="button" onClick={() => setAttempt((current) => current + 1)}>
                    {t("common.tryAgain")}
                </Button>
            </div>
        );
    }

    if (status !== "ready") {
        return (
            <div className="flex min-h-svh items-center justify-center text-sm text-base-content/70">
                {t("session.loading")}
            </div>
        );
    }

    const isLogin = location.pathname === "/login";
    if (!user && !isLogin) {
        return <Navigate to="/login" replace/>;
    }
    if (user && isLogin) {
        return <Navigate to="/" replace/>;
    }

    return <Outlet/>;
}
