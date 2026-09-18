import {zodResolver} from "@hookform/resolvers/zod";
import {CircleAlert} from "lucide-react";
import {useForm} from "react-hook-form";
import {useNavigate} from "react-router";

import {login} from "@pages/login/api/login";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {useSessionStore} from "@/shared/auth/session-store";
import {Button} from "@/components/ui/button";
import {Field, FieldError, FieldGroup, FieldLabel} from "@/components/ui/field";
import {Input} from "@/components/ui/input";
import {type LoginFormData, loginSchema} from "@pages/login/schema/schema";

export function LoginForm() {
    const navigate = useNavigate();
    const setUser = useSessionStore((state) => state.setUser);
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
                message: getApiErrorMessage(error, "Could not sign in. Try again."),
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
                ) : null}

                <Field data-invalid={!!errors.email || undefined}>
                    <FieldLabel htmlFor="login-email">Email</FieldLabel>
                    <Input
                        id="login-email"
                        type="email"
                        placeholder="name@company.com"
                        autoComplete="email"
                        aria-invalid={!!errors.email || undefined}
                        aria-describedby={errors.email ? emailErrorId : undefined}
                        {...register("email")}
                    />
                    <FieldError id={emailErrorId} errors={[errors.email]}/>
                </Field>

                <Field data-invalid={!!errors.password || undefined}>
                    <FieldLabel htmlFor="login-password">Password</FieldLabel>
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

                <div className="flex items-center justify-between gap-4 text-sm">
                    <label className="flex cursor-pointer items-center gap-2 text-muted-foreground">
                        <input
                            type="checkbox"
                            name="remember"
                            className="size-3.5 rounded border border-input accent-primary"
                        />
                        Remember me
                    </label>
                    <Button type="button" variant="link" className="h-auto px-0">
                        Forgot password?
                    </Button>
                </div>

                <Button
                    type="submit"
                    className="mt-1 w-full"
                    size="lg"
                    disabled={isSubmitting}
                >
                    {isSubmitting ? "Signing in…" : "Sign in"}
                </Button>
            </FieldGroup>
        </form>
    );
}
