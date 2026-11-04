import {zodResolver} from "@hookform/resolvers/zod";
import {CircleAlert} from "lucide-react";
import {useMemo} from "react";
import {Controller, useForm} from "react-hook-form";

import {Button} from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import {Field, FieldError, FieldGroup, FieldLabel} from "@/components/ui/field";
import {Input} from "@/components/ui/input";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {getApiErrorCode, getApiErrorMessage} from "@/shared/lib/api/errors";
import {can} from "@/shared/lib/api/me";
import {createUser, updateUser} from "@pages/users/list/api/users";
import type {UserListItem} from "@pages/users/list/model/users";
import {
    createUserFormSchema,
    type UserFormData,
} from "@pages/users/list/schema/userForm";
import {RolePicker} from "@pages/users/list/ui/RolePicker";

type UserFormDialogProps = {
    open: boolean;
    user: UserListItem | null;
    onOpenChange: (open: boolean) => void;
    onSaved: () => void;
};

function defaultValues(user: UserListItem | null): UserFormData {
    return {
        first_name: user?.first_name ?? "",
        last_name: user?.last_name ?? "",
        email: user?.email ?? "",
        password: "",
        role_keys: user?.roles.map((role) => role.key) ?? [],
    };
}

export function UserFormDialog({
    open,
    user,
    onOpenChange,
    onSaved,
}: UserFormDialogProps) {
    const {t} = useI18n();
    const mode = user ? "edit" : "create";
    const canListRoles = can("roles.list");
    const schema = useMemo(() => createUserFormSchema(t, mode), [t, mode]);
    const {
        register,
        control,
        handleSubmit,
        setError,
        formState: {errors, isSubmitting},
    } = useForm<UserFormData>({
        resolver: zodResolver(schema),
        defaultValues: defaultValues(user),
    });

    const onSubmit = async (data: UserFormData) => {
        const payload = {
            first_name: data.first_name,
            last_name: data.last_name,
            email: data.email,
            role_keys: data.role_keys,
            ...(data.password.length > 0 ? {password: data.password} : {}),
        };
        try {
            if (user) {
                await updateUser(user.id, payload);
            } else {
                await createUser({...payload, password: data.password});
            }
            onSaved();
            onOpenChange(false);
        } catch (error) {
            if (getApiErrorCode(error) === "conflict") {
                setError("email", {
                    message: getApiErrorMessage(
                        error,
                        t("users.form.emailConflict"),
                    ),
                });
                return;
            }
            setError("root", {
                message: getApiErrorMessage(
                    error,
                    user ? t("users.form.updateError") : t("users.form.createError"),
                ),
            });
        }
    };

    const firstNameErrorId = "user-first-name-error";
    const lastNameErrorId = "user-last-name-error";
    const emailErrorId = "user-email-error";
    const passwordErrorId = "user-password-error";

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-md" showCloseButton>
                <DialogHeader>
                    <DialogTitle>
                        {user ? t("users.form.editTitle") : t("users.form.createTitle")}
                    </DialogTitle>
                    <DialogDescription className="sr-only">
                        {user ? t("users.form.editTitle") : t("users.form.createTitle")}
                    </DialogDescription>
                </DialogHeader>

                <form
                    id="user-form"
                    className="grid gap-4"
                    noValidate
                    onSubmit={handleSubmit(onSubmit)}
                >
                    <FieldGroup>
                        {errors.root?.message ? (
                            <div
                                role="alert"
                                className="d-alert d-alert-error d-alert-soft items-start text-sm"
                            >
                                <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden/>
                                <p>{errors.root.message}</p>
                            </div>
                        ) : null}

                        <div className="grid gap-4 sm:grid-cols-2">
                            <Field data-invalid={!!errors.first_name || undefined}>
                                <FieldLabel htmlFor="user-first-name">
                                    {t("users.form.firstName")}
                                </FieldLabel>
                                <Input
                                    id="user-first-name"
                                    autoComplete="given-name"
                                    aria-invalid={!!errors.first_name || undefined}
                                    aria-describedby={
                                        errors.first_name ? firstNameErrorId : undefined
                                    }
                                    {...register("first_name")}
                                />
                                <FieldError id={firstNameErrorId} errors={[errors.first_name]}/>
                            </Field>
                            <Field data-invalid={!!errors.last_name || undefined}>
                                <FieldLabel htmlFor="user-last-name">
                                    {t("users.form.lastName")}
                                </FieldLabel>
                                <Input
                                    id="user-last-name"
                                    autoComplete="family-name"
                                    aria-invalid={!!errors.last_name || undefined}
                                    aria-describedby={
                                        errors.last_name ? lastNameErrorId : undefined
                                    }
                                    {...register("last_name")}
                                />
                                <FieldError id={lastNameErrorId} errors={[errors.last_name]}/>
                            </Field>
                        </div>

                        <Field data-invalid={!!errors.email || undefined}>
                            <FieldLabel htmlFor="user-email">{t("common.email")}</FieldLabel>
                            <Input
                                id="user-email"
                                type="email"
                                autoComplete="email"
                                aria-invalid={!!errors.email || undefined}
                                aria-describedby={errors.email ? emailErrorId : undefined}
                                {...register("email")}
                            />
                            <FieldError id={emailErrorId} errors={[errors.email]}/>
                        </Field>

                        <Field data-invalid={!!errors.password || undefined}>
                            <FieldLabel htmlFor="user-password">
                                {user ? t("users.form.newPassword") : t("common.password")}
                            </FieldLabel>
                            <Input
                                id="user-password"
                                type="password"
                                autoComplete="new-password"
                                aria-invalid={!!errors.password || undefined}
                                aria-describedby={
                                    errors.password ? passwordErrorId : undefined
                                }
                                {...register("password")}
                            />
                            <FieldError id={passwordErrorId} errors={[errors.password]}/>
                        </Field>

                        <fieldset className="flex min-h-0 flex-col gap-2">
                            <legend className="text-sm font-medium">
                                {t("users.form.roles")}
                            </legend>
                            {canListRoles ? (
                                <Controller
                                    name="role_keys"
                                    control={control}
                                    render={({field}) => (
                                        <RolePicker
                                            key={open ? "open" : "closed"}
                                            value={field.value}
                                            onChange={field.onChange}
                                            enabled={open}
                                            lockedKeys={
                                                user?.is_last_admin ? ["admin"] : []
                                            }
                                            lockedReason={t("users.form.adminRoleLocked")}
                                        />
                                    )}
                                />
                            ) : (
                                <p className="text-sm text-base-content/70">
                                    {t("users.form.noRolesPermission")}
                                </p>
                            )}
                        </fieldset>
                    </FieldGroup>
                </form>

                <DialogFooter>
                    <Button
                        type="button"
                        variant="outline"
                        disabled={isSubmitting}
                        onClick={() => onOpenChange(false)}
                    >
                        {t("common.cancel")}
                    </Button>
                    <Button type="submit" form="user-form" disabled={isSubmitting}>
                        {isSubmitting
                            ? user
                                ? t("common.saving")
                                : t("common.creating")
                            : user
                              ? t("common.saveChanges")
                              : t("users.form.createTitle")}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
