import {useEffect, useState} from "react";
import {zodResolver} from "@hookform/resolvers/zod";
import {CircleAlert} from "lucide-react";
import {Controller, useForm} from "react-hook-form";

import {Button} from "@/components/ui/button";
import {Checkbox} from "@/components/ui/checkbox";
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
import {getApiErrorCode, getApiErrorMessage} from "@/shared/lib/api/errors";
import {createUser, getRoles, updateUser} from "@pages/users/list/api/users";
import type {RoleRef, UserListItem} from "@pages/users/list/model/users";
import {
    createUserFormSchema,
    type UserFormData,
} from "@pages/users/list/schema/userForm";

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
    const mode = user ? "edit" : "create";
    const rolesKey = user == null ? "create" : String(user.id);
    const [rolesReloadKey, setRolesReloadKey] = useState(0);
    const [rolesLoad, setRolesLoad] = useState<
        | {key: string; status: "ready"; roles: RoleRef[]}
        | {key: string; status: "error"; message: string}
        | null
    >(null);
    const {
        register,
        control,
        handleSubmit,
        setError,
        formState: {errors, isSubmitting},
    } = useForm<UserFormData>({
        resolver: zodResolver(createUserFormSchema(mode)),
        defaultValues: defaultValues(user),
    });

    useEffect(() => {
        if (!open) {
            return;
        }
        let cancelled = false;
        void getRoles()
            .then((roles) => {
                if (!cancelled) {
                    setRolesLoad({key: rolesKey, status: "ready", roles});
                }
            })
            .catch((reason) => {
                if (!cancelled) {
                    setRolesLoad({
                        key: rolesKey,
                        status: "error",
                        message: getApiErrorMessage(reason, "Could not load roles."),
                    });
                }
            });
        return () => {
            cancelled = true;
        };
    }, [open, rolesKey, rolesReloadKey]);

    const rolesCurrent = rolesLoad?.key === rolesKey ? rolesLoad : null;
    const roles = rolesCurrent?.status === "ready" ? rolesCurrent.roles : null;
    const rolesError =
        rolesCurrent?.status === "error" ? rolesCurrent.message : null;
    const rolesReady = roles != null;
    const saveDisabledReason = rolesError
        ? "Roles could not be loaded. Try again."
        : !rolesReady
          ? "Roles are still loading."
          : undefined;

    const onSubmit = async (data: UserFormData) => {
        if (!rolesReady) {
            return;
        }
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
                        "A user with this email already exists",
                    ),
                });
                return;
            }
            setError("root", {
                message: getApiErrorMessage(
                    error,
                    user ? "Could not update user." : "Could not create user.",
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
                    <DialogTitle>{user ? "Edit user" : "Create user"}</DialogTitle>
                    <DialogDescription className="sr-only">
                        {user ? "Edit user" : "Create user"}
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
                                className="flex gap-2.5 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2.5 text-sm text-destructive"
                            >
                                <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden/>
                                <p>{errors.root.message}</p>
                            </div>
                        ) : null}

                        <div className="grid gap-4 sm:grid-cols-2">
                            <Field data-invalid={!!errors.first_name || undefined}>
                                <FieldLabel htmlFor="user-first-name">First name</FieldLabel>
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
                                <FieldLabel htmlFor="user-last-name">Last name</FieldLabel>
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
                            <FieldLabel htmlFor="user-email">Email</FieldLabel>
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
                                {user ? "New password" : "Password"}
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
                            <legend className="text-sm font-medium">Roles</legend>
                            {rolesError ? (
                                <div className="flex flex-col items-start gap-2">
                                    <p className="text-sm text-destructive">{rolesError}</p>
                                    <Button
                                        type="button"
                                        variant="outline"
                                        size="sm"
                                        onClick={() => {
                                            setRolesLoad(null);
                                            setRolesReloadKey((key) => key + 1);
                                        }}
                                    >
                                        Try again
                                    </Button>
                                </div>
                            ) : roles == null ? (
                                <p className="text-sm text-muted-foreground">Loading roles…</p>
                            ) : roles.length === 0 ? (
                                <p className="text-sm text-muted-foreground">
                                    No roles are available.
                                </p>
                            ) : (
                                <Controller
                                    name="role_keys"
                                    control={control}
                                    render={({field}) => (
                                        <div className="max-h-40 overflow-y-auto rounded-lg border border-input">
                                            {roles.map((role) => {
                                                const checkboxId = `user-role-${role.key}`;
                                                const adminLocked =
                                                    role.key === "admin" &&
                                                    Boolean(user?.is_last_admin);
                                                return (
                                                    <label
                                                        key={role.key}
                                                        htmlFor={checkboxId}
                                                        className={`flex items-center gap-2 border-b border-input px-3 py-2 text-sm last:border-b-0 ${
                                                            adminLocked
                                                                ? "cursor-not-allowed opacity-70"
                                                                : "cursor-pointer"
                                                        }`}
                                                    >
                                                        <Checkbox
                                                            id={checkboxId}
                                                            disabled={adminLocked}
                                                            title={
                                                                adminLocked
                                                                    ? "The Admin role cannot be removed from the last admin"
                                                                    : undefined
                                                            }
                                                            checked={
                                                                adminLocked ||
                                                                field.value.includes(role.key)
                                                            }
                                                            onCheckedChange={(checked) => {
                                                                if (adminLocked) {
                                                                    return;
                                                                }
                                                                const selected = new Set(field.value);
                                                                if (checked) {
                                                                    selected.add(role.key);
                                                                } else {
                                                                    selected.delete(role.key);
                                                                }
                                                                field.onChange([...selected]);
                                                            }}
                                                        />
                                                        {role.name}
                                                    </label>
                                                );
                                            })}
                                        </div>
                                    )}
                                />
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
                        Cancel
                    </Button>
                    <Button
                        type="submit"
                        form="user-form"
                        disabled={isSubmitting || !rolesReady}
                        title={saveDisabledReason}
                    >
                        {isSubmitting
                            ? user
                                ? "Saving…"
                                : "Creating…"
                            : user
                              ? "Save changes"
                              : "Create user"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
