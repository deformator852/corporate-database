import {zodResolver} from "@hookform/resolvers/zod";
import {CircleAlert} from "lucide-react";
import {useMemo} from "react";
import {useForm} from "react-hook-form";

import {Button} from "@/components/ui/button";
import {Card} from "@/components/ui/card";
import {Field, FieldError, FieldGroup, FieldLabel} from "@/components/ui/field";
import {Input} from "@/components/ui/input";
import {useSessionStore} from "@/shared/auth/session-store";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {changePassword} from "@pages/account/api/account";
import {createPasswordChangeSchema, type PasswordChangeFormData} from "@pages/account/schema/passwordChange";

const FIELDS = [
    {name: "current", label: "account.currentPassword", autoComplete: "current-password"},
    {name: "next", label: "account.newPassword", autoComplete: "new-password"},
    {name: "confirm", label: "account.confirmPassword", autoComplete: "new-password"},
] as const;

/** The signed-in user's own account: who they are, and their password. */
export function Account() {
    const {t} = useI18n();
    const user = useSessionStore((state) => state.user);
    const schema = useMemo(() => createPasswordChangeSchema(t), [t]);
    const {
        register,
        handleSubmit,
        setError,
        formState: {errors, isSubmitting},
    } = useForm<PasswordChangeFormData>({
        resolver: zodResolver(schema),
        defaultValues: {current: "", next: "", confirm: ""},
    });

    const onSubmit = async (data: PasswordChangeFormData) => {
        try {
            await changePassword(data.current, data.next);
            // The server ended every session, this one too.
            useSessionStore.getState().clear(t("account.passwordChanged"));
        } catch (error) {
            setError("root", {message: getApiErrorMessage(error, t("account.passwordError"))});
        }
    };

    if (user == null) {
        return null;
    }
    const header = (
        <div className="stack">
            <h1>{t("account.title")}</h1>
            <p className="text-muted-foreground">
                {`${user.first_name} ${user.last_name}`.trim()} · {user.email}
            </p>
        </div>
    );
    if (!user.uses_password) {
        // Signs in through SSO: the password lives at the company's provider.
        return (
            <div className="stack stack--lg w-full">
                {header}
                <Card className="gap-1 px-4 py-4 sm:px-5 sm:py-5">
                    <h2 className="text-lg">{t("account.ssoTitle")}</h2>
                    <p className="text-sm text-muted-foreground">{t("account.ssoHint")}</p>
                </Card>
            </div>
        );
    }
    return (
        <div className="stack stack--lg w-full">
            {header}

            <Card className="gap-4 px-4 py-4 sm:px-5 sm:py-5">
                <div className="space-y-1">
                    <h2 className="text-lg">{t("account.passwordTitle")}</h2>
                    <p className="text-sm text-muted-foreground">{t("account.passwordHint")}</p>
                </div>
                <form className="stack" noValidate onSubmit={(event) => void handleSubmit(onSubmit)(event)}>
                    <FieldGroup>
                        {errors.root?.message ? (
                            <div
                                role="alert"
                                className="flex gap-2.5 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2.5 text-sm text-destructive"
                            >
                                <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
                                <p>{errors.root.message}</p>
                            </div>
                        ) : null}
                        {FIELDS.map((field) => {
                            const id = `account-${field.name}`;
                            const error = errors[field.name];
                            return (
                                <Field key={field.name} data-invalid={!!error || undefined}>
                                    <FieldLabel htmlFor={id}>{t(field.label)}</FieldLabel>
                                    <Input
                                        id={id}
                                        type="password"
                                        autoComplete={field.autoComplete}
                                        maxLength={100}
                                        disabled={isSubmitting}
                                        aria-invalid={!!error || undefined}
                                        aria-describedby={error ? `${id}-error` : undefined}
                                        {...register(field.name)}
                                    />
                                    <FieldError id={`${id}-error`} errors={[error]} />
                                </Field>
                            );
                        })}
                    </FieldGroup>
                    <Button type="submit" className="w-fit" disabled={isSubmitting}>
                        {isSubmitting ? t("common.saving") : t("account.changePassword")}
                    </Button>
                </form>
            </Card>
        </div>
    );
}
