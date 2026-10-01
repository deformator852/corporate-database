import {zodResolver} from "@hookform/resolvers/zod";
import {cn} from "cn";
import {CircleAlert, FileUp} from "lucide-react";
import {useMemo, useRef, useState, type DragEvent} from "react";
import {useForm} from "react-hook-form";

import {Button} from "@/components/ui/button";
import {Field, FieldError, FieldGroup, FieldLabel} from "@/components/ui/field";
import {Input} from "@/components/ui/input";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {documentClassificationKey} from "@/shared/i18n/keys";
import {can} from "@/shared/lib/api/me";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {uploadDocument} from "@pages/documents/api/documents";
import {
    DOCUMENT_ACCEPT,
    allowedUploadClassifications,
    fileStem,
    type DocumentListItem,
} from "@pages/documents/model/documents";
import {
    createDocumentUploadSchema,
    type DocumentUploadFormData,
} from "@pages/documents/schema/documentUpload";

type DocumentUploadFormProps = {
    onUploaded?: (document: DocumentListItem) => void;
};

export function DocumentUploadForm({onUploaded}: DocumentUploadFormProps) {
    const {t} = useI18n();
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [dragging, setDragging] = useState(false);
    const [success, setSuccess] = useState<string | null>(null);
    const schema = useMemo(() => createDocumentUploadSchema(t), [t]);
    const {
        register,
        handleSubmit,
        setValue,
        getValues,
        setError,
        watch,
        reset,
        formState: {errors, isSubmitting},
    } = useForm<DocumentUploadFormData>({
        resolver: zodResolver(schema),
        defaultValues: {
            name: "",
            classification: "standard",
        },
    });

    const file = watch("file");
    const nameRegister = register("name");
    const classificationRegister = register("classification");
    const classifications = allowedUploadClassifications(
        can("documents.restricted"),
        can("documents.confidential"),
        can("documents.secret"),
    );

    function assignFile(next: File | undefined) {
        if (next == null) {
            return;
        }
        setSuccess(null);
        // Replace the name unless the user typed one: an empty name, or the
        // one filled in from the previous file (e.g. after a failed upload).
        const previous = getValues("file");
        const name = getValues("name").trim();
        if (!name || (previous instanceof File && name === fileStem(previous.name))) {
            setValue("name", fileStem(next.name), {shouldValidate: true});
        }
        setValue("file", next, {shouldValidate: true, shouldTouch: true});
    }

    function handleDragOver(event: DragEvent<HTMLDivElement>) {
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
        setDragging(true);
    }

    function handleDragLeave(event: DragEvent<HTMLDivElement>) {
        if (event.currentTarget.contains(event.relatedTarget as Node | null)) {
            return;
        }
        setDragging(false);
    }

    function handleDrop(event: DragEvent<HTMLDivElement>) {
        event.preventDefault();
        event.stopPropagation();
        setDragging(false);
        if (isSubmitting) {
            return;
        }
        assignFile(event.dataTransfer.files[0]);
    }

    async function onSubmit(data: DocumentUploadFormData) {
        setSuccess(null);
        try {
            const accepted = await uploadDocument(
                data.name,
                data.file,
                data.classification,
            );
            reset({name: "", classification: "standard"});
            if (fileInputRef.current) {
                fileInputRef.current.value = "";
            }
            onUploaded?.(accepted);
            setSuccess(
                accepted.converted
                    ? t("documents.upload.successConverted")
                    : t("documents.upload.success"),
            );
        } catch (error) {
            setError("root", {
                message: getApiErrorMessage(error, t("documents.upload.error")),
            });
        }
    }

    const nameErrorId = "document-name-error";
    const fileErrorId = "document-file-error";

    return (
        <form className="stack" noValidate onSubmit={handleSubmit(onSubmit)}>
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

                {success ? (
                    <p role="status" className="text-sm text-muted-foreground">
                        {success}
                    </p>
                ) : null}

                <Field data-invalid={!!errors.name || undefined}>
                    <FieldLabel htmlFor="document-name">
                        {t("documents.upload.name")}
                    </FieldLabel>
                    <Input
                        id="document-name"
                        autoComplete="off"
                        maxLength={200}
                        disabled={isSubmitting}
                        aria-invalid={!!errors.name || undefined}
                        aria-describedby={errors.name ? nameErrorId : undefined}
                        {...nameRegister}
                    />
                    <FieldError id={nameErrorId} errors={[errors.name]} />
                </Field>

                <Field data-invalid={!!errors.classification || undefined}>
                    <FieldLabel htmlFor="document-classification">
                        {t("common.access")}
                    </FieldLabel>
                    <select
                        id="document-classification"
                        disabled={isSubmitting}
                        aria-invalid={!!errors.classification || undefined}
                        aria-describedby={
                            errors.classification
                                ? "document-classification-error"
                                : undefined
                        }
                        className={cn(
                            "h-8 w-full min-w-0 cursor-pointer rounded-lg border border-input bg-transparent px-2.5 py-1 text-base outline-none transition-colors md:text-sm",
                            "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
                            "disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-input/50 disabled:opacity-50",
                            "aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20",
                            "dark:bg-input/30 dark:disabled:bg-input/80",
                        )}
                        {...classificationRegister}
                    >
                        {classifications.map((value) => (
                            <option key={value} value={value}>
                                {t(documentClassificationKey(value))}
                            </option>
                        ))}
                    </select>
                    <FieldError
                        id="document-classification-error"
                        errors={[errors.classification]}
                    />
                </Field>

                <Field data-invalid={!!errors.file || undefined}>
                    <FieldLabel htmlFor="document-file">{t("common.file")}</FieldLabel>
                    <div
                        className={`cursor-pointer rounded-lg border border-dashed px-4 py-6 text-center transition-colors ${
                            dragging
                                ? "border-ring bg-accent"
                                : "border-input"
                        }`}
                        onClick={() => {
                            if (!isSubmitting) {
                                fileInputRef.current?.click();
                            }
                        }}
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                    >
                        <FileUp className="mx-auto mb-2 size-5 text-muted-foreground" aria-hidden />
                        <p className="text-sm">{t("documents.upload.dropPrompt")}</p>
                        <p className="mt-1 text-sm text-muted-foreground">
                            {file ? file.name : t("documents.upload.dropHint")}
                        </p>
                    </div>
                    <input
                        id="document-file"
                        ref={fileInputRef}
                        type="file"
                        accept={DOCUMENT_ACCEPT}
                        disabled={isSubmitting}
                        className="sr-only"
                        aria-invalid={!!errors.file || undefined}
                        aria-describedby={errors.file ? fileErrorId : undefined}
                        onChange={(event) => {
                            assignFile(event.target.files?.[0]);
                        }}
                    />
                    <FieldError id={fileErrorId} errors={[errors.file]} />
                </Field>
            </FieldGroup>

            <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? t("common.uploading") : t("documents.upload.submit")}
            </Button>
        </form>
    );
}
