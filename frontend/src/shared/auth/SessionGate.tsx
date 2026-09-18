import {useEffect} from "react";
import {Navigate, Outlet, useLocation} from "react-router";

import {getMe} from "@/shared/lib/api/me";
import {useSessionStore} from "@/shared/auth/session-store";

export function SessionGate() {
    const status = useSessionStore((state) => state.status);
    const user = useSessionStore((state) => state.user);
    const location = useLocation();

    useEffect(() => {
        const {status: current, setUser, clear} = useSessionStore.getState();
        if (current === "ready") {
            return;
        }

        useSessionStore.setState({status: "loading"});

        let cancelled = false;
        void getMe()
            .then((nextUser) => {
                if (!cancelled) {
                    setUser(nextUser);
                }
            })
            .catch(() => {
                if (!cancelled) {
                    clear();
                }
            });

        return () => {
            cancelled = true;
        };
    }, []);

    if (status !== "ready") {
        return (
            <div className="flex min-h-svh items-center justify-center text-sm text-muted-foreground">
                Loading session…
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
