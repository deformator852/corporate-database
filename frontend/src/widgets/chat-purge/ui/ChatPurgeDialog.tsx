import {zodResolver} from "@hookform/resolvers/zod";
import {CircleAlert} from "lucide-react";
import {useMemo} from "react";
import {useForm, useWatch} from "react-hook-form";

import {
    AlertDialog,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {Button} from "@/components/ui/button";
import {Field, FieldError, FieldGroup, FieldLabel} from "@/components/ui/field";
import {Input} from "@/components/ui/input";
import {NativeSelect, NativeSelectOption} from "@/components/ui/native-select";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {purgeChats} from "@/widgets/chat-purge/api/purge";
import {
    createPurgeSchema,
    PURGE_PERIODS,
    purgePeriodKey,
    purgeRange,
    type PurgeFormData,
} from "@/widgets/chat-purge/model/purge";

type ChatPurgeDialogProps = {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    /** Only this user's chats; without it, everyone's the actor may reach. */
    user?: {id: number; name: string};
    /** Called with how many chats were deleted. */
    onPurged: (deleted: number) => void;
};

/** Deletes saved chats, all or those last active in a period. */
export function ChatPurgeDialog({open, onOpenChange, user, onPurged}: ChatPurgeDialogProps) {
    const {t} = useI18n();
    const schema = useMemo(() => createPurgeSchema(t), [t]);
    const {
        register,
        control,
        handleSubmit,
        setError,
        reset,
        formState: {errors, isSubmitting},
    } = useForm<PurgeFormData>({
        resolver: zodResolver(schema),
        // The narrowest choice first: a slip must not delete everything.
        defaultValues: {period: "day", from: "", to: ""},
    });
    const period = useWatch({control, name: "period"});

    const onSubmit = async (data: PurgeFormData) => {
        try {
            onPurged(await purgeChats(purgeRange(data), user?.id));
            reset();
            onOpenChange(false);
        } catch (error) {
            setError("root", {message: getApiErrorMessage(error, t("chatPurge.error"))});
        }
    };

    return (
        <AlertDialog open={open} onOpenChange={(next) => !isSubmitting && onOpenChange(next)}>
            <AlertDialogContent>
                <AlertDialogHeader>
                    <AlertDialogTitle>
                        {user ? t("chatPurge.titleUser", {name: user.name}) : t("chatPurge.title")}
                    </AlertDialogTitle>
                    <AlertDialogDescription>{t("chatPurge.description")}</AlertDialogDescription>
                </AlertDialogHeader>

                <form
                    id="chat-purge-form"
                    noValidate
                    onSubmit={(event) => void handleSubmit(onSubmit)(event)}
                >
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
                        <Field>
                            <FieldLabel htmlFor="chat-purge-period">{t("chatPurge.period")}</FieldLabel>
                            <NativeSelect id="chat-purge-period" className="w-full" {...register("period")}>
                                {PURGE_PERIODS.map((value) => (
                                    <NativeSelectOption key={value} value={value}>
                                        {t(purgePeriodKey(value))}
                                    </NativeSelectOption>
                                ))}
                            </NativeSelect>
                        </Field>
                        {period === "custom" ? (
                            <div className="grid gap-3 sm:grid-cols-2">
                                <Field>
                                    <FieldLabel htmlFor="chat-purge-from">{t("chatPurge.from")}</FieldLabel>
                                    <Input id="chat-purge-from" type="date" {...register("from")} />
                                </Field>
                                <Field data-invalid={!!errors.to || undefined}>
                                    <FieldLabel htmlFor="chat-purge-to">{t("chatPurge.to")}</FieldLabel>
                                    <Input
                                        id="chat-purge-to"
                                        type="date"
                                        aria-invalid={!!errors.to || undefined}
                                        aria-describedby={errors.to ? "chat-purge-to-error" : undefined}
                                        {...register("to")}
                                    />
                                </Field>
                                <FieldError id="chat-purge-to-error" className="sm:col-span-2" errors={[errors.to]} />
                            </div>
                        ) : null}
                    </FieldGroup>
                </form>

                <AlertDialogFooter>
                    <AlertDialogCancel disabled={isSubmitting}>{t("common.cancel")}</AlertDialogCancel>
                    <Button type="submit" form="chat-purge-form" variant="destructive" disabled={isSubmitting}>
                        {isSubmitting ? t("chatPurge.clearing") : t("chatPurge.clear")}
                    </Button>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    );
}
