import {zodResolver} from "@hookform/resolvers/zod";
import {CircleAlert, FileUp} from "lucide-react";
import {useMemo, useRef, useState, type DragEvent, type RefObject} from "react";
import {useForm, useWatch} from "react-hook-form";

import {Button} from "@/components/ui/button";
import {NativeSelect} from "@/components/ui/native-select";
import {Field, FieldError, FieldGroup, FieldLabel} from "@/components/ui/field";
import {Input} from "@/components/ui/input";
import {useI18n, type TranslateFn} from "@/shared/i18n/I18nProvider";
import {documentClassificationKey} from "@/entities/document/model";
import {can} from "@/shared/lib/api/me";
import {uploadFiles} from "@pages/documents/model/uploadFiles";
import {SelectedFiles} from "@pages/documents/ui/SelectedFiles";
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
    const [success, setSuccess] = useState<string | null>(null);
    // Files sent so far while uploading several, one request per file.
    const [sent, setSent] = useState(0);
    // Server reasons for files that were not uploaded; they stay selected.
    const [failures, setFailures] = useState(new Map<File, string>());
    const schema = useMemo(() => createDocumentUploadSchema(t), [t]);
    const {
        register,
        handleSubmit,
        setValue,
        getValues,
        setError,
        reset,
        control,
        formState: {errors, isSubmitting},
    } = useForm<DocumentUploadFormData>({
        resolver: zodResolver(schema),
        defaultValues: {
            name: "",
            classification: "standard",
            files: [],
        },
    });

    const files = useWatch({control, name: "files"});
    const several = files.length > 1;
    // Files left after a batch upload keep their list and reasons.
    const listed = several || failures.size > 0;
    const nameRegister = register("name");
    const classificationRegister = register("classification");
    const classifications = allowedUploadClassifications(
        can("documents.restricted"),
        can("documents.confidential"),
        can("documents.secret"),
    );

    function assignFiles(next: File[]) {
        if (next.length === 0) {
            return;
        }
        setSuccess(null);
        setFailures(new Map());
        // A single file fills the name unless the user typed one: an empty
        // name, or the one filled in from the previous file (e.g. after a
        // failed upload).
        const previous = getValues("files");
        const name = getValues("name").trim();
        if (
            next.length === 1 &&
            (!name || (previous.length === 1 && name === fileStem(previous[0].name)))
        ) {
            setValue("name", fileStem(next[0].name), {shouldValidate: true});
        }
        setValue("files", next, {shouldValidate: true, shouldTouch: true});
    }

    function removeFile(file: File) {
        setValue(
            "files",
            getValues("files").filter((item) => item !== file),
            {shouldValidate: true},
        );
    }

    async function onSubmit(data: DocumentUploadFormData) {
        setSuccess(null);
        const {failed, converted} = await uploadFiles({
            files: data.files,
            name: data.name,
            classification: data.classification,
            errorFallback: t("documents.upload.error"),
            onProgress: setSent,
            onUploaded,
        });
        if (fileInputRef.current) {
            fileInputRef.current.value = "";
        }
        // One file shows its reason in the alert; a batch lists each one.
        setFailures(data.files.length > 1 ? failed : new Map());
        if (failed.size === 0) {
            reset({name: "", classification: data.classification, files: []});
            setSuccess(successMessage(t, data.files.length, converted));
            return;
        }
        setValue("files", [...failed.keys()]);
        if (failed.size === 1 && data.files.length > 1) {
            setValue("name", fileStem([...failed.keys()][0].name));
        }
        setError("root", {
            message:
                data.files.length === 1
                    ? [...failed.values()][0]
                    : t("documents.upload.someFailed", {
                          failed: failed.size,
                          total: data.files.length,
                      }),
        });
    }

    const nameErrorId = "document-name-error";
    const fileErrorId = "document-file-error";
    // No file chosen, or the one chosen file is invalid; with several files
    // each one's problem shows in the list.
    const fileError =
        errors.files?.message ?? (several ? undefined : errors.files?.[0]?.message);

    return (
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

                {success ? (
                    <p role="status" className="text-sm text-muted-foreground">
                        {success}
                    </p>
                ) : null}

                {several ? null : (
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
                )}

                <Field data-invalid={!!errors.classification || undefined}>
                    <FieldLabel htmlFor="document-classification">
                        {t("common.access")}
                    </FieldLabel>
                    <NativeSelect
                        id="document-classification"
                        className="w-full"
                        disabled={isSubmitting}
                        aria-invalid={!!errors.classification || undefined}
                        aria-describedby={
                            errors.classification
                                ? "document-classification-error"
                                : undefined
                        }
                        {...classificationRegister}
                    >
                        {classifications.map((value) => (
                            <option key={value} value={value}>
                                {t(documentClassificationKey(value))}
                            </option>
                        ))}
                    </NativeSelect>
                    <FieldError
                        id="document-classification-error"
                        errors={[errors.classification]}
                    />
                </Field>

                <Field data-invalid={!!fileError || undefined}>
                    <FieldLabel htmlFor="document-file">{t("common.file")}</FieldLabel>
                    <FileDropZone
                        inputRef={fileInputRef}
                        disabled={isSubmitting}
                        summary={
                            several
                                ? t("documents.upload.filesSelected", {count: files.length})
                                : (files[0]?.name ?? t("documents.upload.dropHint"))
                        }
                        errorId={fileError ? fileErrorId : undefined}
                        onFiles={assignFiles}
                    />
                    <FieldError id={fileErrorId} errors={[fileError ? {message: fileError} : undefined]} />
                    {listed ? (
                        <>
                            {several ? (
                                <p className="text-sm text-muted-foreground">
                                    {t("documents.upload.namesFromFiles")}
                                </p>
                            ) : null}
                            <SelectedFiles
                                files={files}
                                problemOf={(file, index) => failures.get(file) ?? errors.files?.[index]?.message}
                                disabled={isSubmitting}
                                onRemove={removeFile}
                            />
                        </>
                    ) : null}
                </Field>
            </FieldGroup>

            <Button type="submit" disabled={isSubmitting}>
                {!isSubmitting
                    ? t("documents.upload.submit")
                    : several
                      ? t("documents.upload.progress", {done: sent + 1, total: files.length})
                      : t("common.uploading")}
            </Button>
        </form>
    );
}

function successMessage(t: TranslateFn, count: number, converted: boolean): string {
    if (count > 1) {
        return t("documents.upload.successMany", {count});
    }
    return converted ? t("documents.upload.successConverted") : t("documents.upload.success");
}

/** Click to choose files or drop them here. */
function FileDropZone({
    inputRef,
    disabled,
    summary,
    errorId,
    onFiles,
}: {
    inputRef: RefObject<HTMLInputElement | null>;
    disabled: boolean;
    /** The chosen files, or a hint while there are none. */
    summary: string;
    /** Set while the files are invalid. */
    errorId?: string;
    onFiles: (files: File[]) => void;
}) {
    const {t} = useI18n();
    const [dragging, setDragging] = useState(false);

    return (
        <div
            className={`relative cursor-pointer rounded-lg border border-dashed px-4 py-6 text-center transition-colors ${
                dragging ? "border-ring bg-accent" : "border-input"
            }`}
            onClick={(event) => {
                // The input's own click bubbles up here: do not reopen it.
                if (!disabled && event.target !== inputRef.current) {
                    inputRef.current?.click();
                }
            }}
            onDragOver={(event) => {
                event.preventDefault();
                event.dataTransfer.dropEffect = "copy";
                setDragging(true);
            }}
            onDragLeave={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                    setDragging(false);
                }
            }}
            onDrop={(event: DragEvent<HTMLDivElement>) => {
                event.preventDefault();
                event.stopPropagation();
                setDragging(false);
                if (!disabled) {
                    onFiles([...event.dataTransfer.files]);
                }
            }}
        >
            <FileUp className="mx-auto mb-2 size-5 text-muted-foreground" aria-hidden />
            <p className="text-sm">{t("documents.upload.dropPrompt")}</p>
            <p className="mt-1 text-sm text-muted-foreground">{summary}</p>
            {/* Inside the drop zone, not a direct child of Field: Field gives
                direct .sr-only children their natural width, which widened
                the page on phones. */}
            <input
                id="document-file"
                ref={inputRef}
                type="file"
                multiple
                accept={DOCUMENT_ACCEPT}
                disabled={disabled}
                className="sr-only"
                aria-invalid={errorId ? true : undefined}
                aria-describedby={errorId}
                onChange={(event) => onFiles([...(event.target.files ?? [])])}
            />
        </div>
    );
}
