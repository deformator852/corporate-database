import {zodResolver} from "@hookform/resolvers/zod";
import {CircleAlert} from "lucide-react";
import {useMemo} from "react";
import {useForm} from "react-hook-form";

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
import {NativeSelect, NativeSelectOption} from "@/components/ui/native-select";
import {documentClassificationKey, type DocumentClassification} from "@/entities/document/model";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {updateDocument} from "@pages/documents/api/documents";
import type {DocumentListItem} from "@pages/documents/model/documents";
import {createDocumentEditSchema, type DocumentEditFormData} from "@pages/documents/schema/documentEdit";

type DocumentEditDialogProps = {
    document: DocumentListItem;
    /** Levels the user may give; the document's own level is one of them. */
    classifications: DocumentClassification[];
    onOpenChange: (open: boolean) => void;
    onSaved: (document: DocumentListItem) => void;
};

/** Rename a document or change its access level. Mounted per document. */
export function DocumentEditDialog({document, classifications, onOpenChange, onSaved}: DocumentEditDialogProps) {
    const {t} = useI18n();
    const schema = useMemo(() => createDocumentEditSchema(t), [t]);
    const {
        register,
        handleSubmit,
        setError,
        formState: {errors, isSubmitting},
    } = useForm<DocumentEditFormData>({
        resolver: zodResolver(schema),
        defaultValues: {name: document.name, classification: document.classification},
    });

    const onSubmit = async (data: DocumentEditFormData) => {
        try {
            onSaved(await updateDocument(document.id, data));
            onOpenChange(false);
        } catch (error) {
            setError("root", {message: getApiErrorMessage(error, t("documents.edit.error"))});
        }
    };

    return (
        <Dialog open onOpenChange={(open) => !isSubmitting && onOpenChange(open)}>
            <DialogContent className="sm:max-w-md" showCloseButton>
                <DialogHeader>
                    <DialogTitle>{t("documents.edit.title")}</DialogTitle>
                    <DialogDescription>{t("documents.edit.description")}</DialogDescription>
                </DialogHeader>

                <form
                    id="document-edit-form"
                    className="grid gap-4"
                    noValidate
                    onSubmit={(event) => void handleSubmit(onSubmit)(event)}
                >
                    <FieldGroup>
                        {errors.root?.message ? (
                            <div
                                role="alert"
                                className="d-alert d-alert-error d-alert-soft items-start text-sm"
                            >
                                <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
                                <p>{errors.root.message}</p>
                            </div>
                        ) : null}

                        <Field data-invalid={!!errors.name || undefined}>
                            <FieldLabel htmlFor="document-edit-name">{t("documents.upload.name")}</FieldLabel>
                            <Input
                                id="document-edit-name"
                                autoComplete="off"
                                maxLength={200}
                                aria-invalid={!!errors.name || undefined}
                                aria-describedby={errors.name ? "document-edit-name-error" : undefined}
                                {...register("name")}
                            />
                            <FieldError id="document-edit-name-error" errors={[errors.name]} />
                        </Field>

                        <Field>
                            <FieldLabel htmlFor="document-edit-classification">{t("common.access")}</FieldLabel>
                            <NativeSelect
                                id="document-edit-classification"
                                className="w-full"
                                {...register("classification")}
                            >
                                {classifications.map((value) => (
                                    <NativeSelectOption key={value} value={value}>
                                        {t(documentClassificationKey(value))}
                                    </NativeSelectOption>
                                ))}
                            </NativeSelect>
                        </Field>
                    </FieldGroup>
                </form>

                <DialogFooter>
                    <Button type="button" variant="outline" disabled={isSubmitting} onClick={() => onOpenChange(false)}>
                        {t("common.cancel")}
                    </Button>
                    <Button type="submit" form="document-edit-form" disabled={isSubmitting}>
                        {isSubmitting ? t("common.saving") : t("common.saveChanges")}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
