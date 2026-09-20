import {zodResolver} from "@hookform/resolvers/zod";
import {CircleAlert} from "lucide-react";
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
import {Textarea} from "@/components/ui/textarea";
import {getApiErrorCode, getApiErrorMessage} from "@/shared/lib/api/errors";
import {can} from "@/shared/lib/api/me";
import {keyFromName} from "@/shared/lib/keyFromName";
import {createRole, updateRole} from "@pages/roles/list/api/roles";
import type {RoleListItem} from "@pages/roles/list/model/roles";
import {roleFormSchema, type RoleFormData} from "@pages/roles/list/schema/roleForm";
import {PermissionPicker} from "@pages/roles/list/ui/PermissionPicker";

type RoleFormDialogProps = {
    open: boolean;
    role: RoleListItem | null;
    onOpenChange: (open: boolean) => void;
    onSaved: () => void;
};

function defaultValues(role: RoleListItem | null): RoleFormData {
    return {
        name: role?.name ?? "",
        description: role?.description ?? "",
        permission_keys: role?.permissions.map((permission) => permission.key) ?? [],
    };
}

export function RoleFormDialog({
    open,
    role,
    onOpenChange,
    onSaved,
}: RoleFormDialogProps) {
    const mode = role ? "edit" : "create";
    const nameLocked = role != null;
    const {
        register,
        control,
        handleSubmit,
        setError,
        watch,
        formState: {errors, isSubmitting},
    } = useForm<RoleFormData>({
        resolver: zodResolver(roleFormSchema(mode)),
        defaultValues: defaultValues(role),
    });
    const canListPermissions = can("permissions.list");
    const derivedKey = role?.key ?? keyFromName(watch("name"));

    const onSubmit = async (data: RoleFormData) => {
        const payload = {
            description: data.description,
            permission_keys: data.permission_keys,
        };
        try {
            if (role) {
                await updateRole(role.key, payload);
            } else {
                await createRole({...payload, name: data.name});
            }
            onSaved();
            onOpenChange(false);
        } catch (error) {
            if (getApiErrorCode(error) === "conflict") {
                setError("name", {
                    message: getApiErrorMessage(
                        error,
                        "A role with this name already exists",
                    ),
                });
                return;
            }
            setError("root", {
                message: getApiErrorMessage(
                    error,
                    role ? "Could not update role." : "Could not create role.",
                ),
            });
        }
    };

    const nameErrorId = "role-name-error";
    const descriptionErrorId = "role-description-error";

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-md" showCloseButton>
                <DialogHeader>
                    <DialogTitle>{role ? "Edit role" : "Create role"}</DialogTitle>
                    <DialogDescription className="sr-only">
                        {role ? "Edit role" : "Create role"}
                    </DialogDescription>
                </DialogHeader>

                <form
                    id="role-form"
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

                        <Field data-invalid={!!errors.name || undefined}>
                            <FieldLabel htmlFor="role-name">Name</FieldLabel>
                            <Input
                                id="role-name"
                                readOnly={nameLocked}
                                autoComplete="off"
                                aria-invalid={!!errors.name || undefined}
                                aria-describedby={errors.name ? nameErrorId : undefined}
                                className={
                                    nameLocked
                                        ? "pointer-events-none cursor-not-allowed bg-input/50 opacity-50"
                                        : undefined
                                }
                                {...register("name")}
                            />
                            {derivedKey ? (
                                <p className="text-sm text-muted-foreground">
                                    Key{" "}
                                    <span className="font-medium text-foreground">
                                        {derivedKey}
                                    </span>
                                </p>
                            ) : null}
                            <FieldError id={nameErrorId} errors={[errors.name]}/>
                        </Field>

                        <Field data-invalid={!!errors.description || undefined}>
                            <FieldLabel htmlFor="role-description">Description</FieldLabel>
                            <Textarea
                                id="role-description"
                                rows={3}
                                aria-invalid={!!errors.description || undefined}
                                aria-describedby={
                                    errors.description ? descriptionErrorId : undefined
                                }
                                {...register("description")}
                            />
                            <FieldError
                                id={descriptionErrorId}
                                errors={[errors.description]}
                            />
                        </Field>

                        <fieldset className="flex min-h-0 flex-col gap-2">
                            <legend className="text-sm font-medium">Permissions</legend>
                            {canListPermissions ? (
                                <Controller
                                    name="permission_keys"
                                    control={control}
                                    render={({field}) => (
                                        <PermissionPicker
                                            key={open ? "open" : "closed"}
                                            value={field.value}
                                            onChange={field.onChange}
                                            enabled={open}
                                        />
                                    )}
                                />
                            ) : (
                                <p className="text-sm text-muted-foreground">
                                    You don't have permission to view permissions.
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
                        Cancel
                    </Button>
                    <Button type="submit" form="role-form" disabled={isSubmitting}>
                        {isSubmitting
                            ? role
                                ? "Saving…"
                                : "Creating…"
                            : role
                              ? "Save changes"
                              : "Create role"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
