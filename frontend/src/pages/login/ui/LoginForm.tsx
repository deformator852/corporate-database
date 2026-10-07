import {zodResolver} from "@hookform/resolvers/zod";
import {CircleAlert} from "lucide-react";
import {useMemo} from "react";
import {useForm} from "react-hook-form";
import {useNavigate} from "react-router";

import {login} from "@pages/login/api/login";
import {createLoginSchema, type LoginFormData} from "@pages/login/schema/loginForm";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {useSessionStore} from "@/shared/auth/session-store";
import {Button} from "@/components/ui/button";
import {Field, FieldError, FieldGroup, FieldLabel} from "@/components/ui/field";
import {Input} from "@/components/ui/input";

export function LoginForm() {
    const {t} = useI18n();
    const navigate = useNavigate();
    const setUser = useSessionStore((state) => state.setUser);
    const notice = useSessionStore((state) => state.notice);
    const loginSchema = useMemo(() => createLoginSchema(t), [t]);
    const {
        register,
        handleSubmit,
        setError,
        formState: {errors, isSubmitting},
    } = useForm<LoginFormData>({
        resolver: zodResolver(loginSchema),
        defaultValues: {
            email: "",
            password: "",
        },
    });

    const onSubmit = async (data: LoginFormData) => {
        try {
            const user = await login(data);
            setUser(user);
            await navigate("/");
        } catch (error) {
            setError("root", {
                message: getApiErrorMessage(error, t("login.errorSignIn")),
            });
        }
    };

    const emailErrorId = "login-email-error";
    const passwordErrorId = "login-password-error";

    return (
        <form
            className="contents"
            noValidate
            onSubmit={handleSubmit(onSubmit)}
        >
            <FieldGroup>
                {errors.root?.message ? (
                    <div
                        role="alert"
                        className="flex gap-2.5 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2.5 text-sm text-destructive"
                    >
                        <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden/>
                        <p>{errors.root.message}</p>
                    </div>
                ) : notice ? (
                    <p role="status" className="rounded-lg bg-muted px-3 py-2.5 text-sm">
                        {notice}
                    </p>
                ) : null}

                <Field data-invalid={!!errors.email || undefined}>
                    <FieldLabel htmlFor="login-email">{t("common.email")}</FieldLabel>
                    <Input
                        id="login-email"
                        type="email"
                        placeholder={t("login.emailPlaceholder")}
                        autoComplete="email"
                        aria-invalid={!!errors.email || undefined}
                        aria-describedby={errors.email ? emailErrorId : undefined}
                        {...register("email")}
                    />
                    <FieldError id={emailErrorId} errors={[errors.email]}/>
                </Field>

                <Field data-invalid={!!errors.password || undefined}>
                    <FieldLabel htmlFor="login-password">{t("common.password")}</FieldLabel>
                    <Input
                        id="login-password"
                        type="password"
                        placeholder="••••••••"
                        autoComplete="current-password"
                        aria-invalid={!!errors.password || undefined}
                        aria-describedby={errors.password ? passwordErrorId : undefined}
                        {...register("password")}
                    />
                    <FieldError id={passwordErrorId} errors={[errors.password]}/>
                </Field>

                <Button
                    type="submit"
                    className="mt-1 w-full"
                    size="lg"
                    disabled={isSubmitting}
                >
                    {isSubmitting ? t("login.signingIn") : t("login.signIn")}
                </Button>

                <p className="text-center text-xs text-muted-foreground">
                    {t("login.forgotHint")}
                </p>
            </FieldGroup>
        </form>
    );
}
