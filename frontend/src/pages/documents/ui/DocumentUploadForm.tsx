import {zodResolver} from "@hookform/resolvers/zod";
import {CircleAlert, FileUp} from "lucide-react";
import {useRef, useState, type DragEvent} from "react";
import {useForm} from "react-hook-form";

import {Button} from "@/components/ui/button";
import {Field, FieldError, FieldGroup, FieldLabel} from "@/components/ui/field";
import {Input} from "@/components/ui/input";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {uploadDocument} from "@pages/documents/api/documents";
import {
    DOCUMENT_ACCEPT,
    fileStem,
    type DocumentListItem,
} from "@pages/documents/model/documents";
import {
    documentUploadSchema,
    type DocumentUploadFormData,
} from "@pages/documents/schema/documentUpload";

type DocumentUploadFormProps = {
    onUploaded?: (document: DocumentListItem) => void;
};

export function DocumentUploadForm({onUploaded}: DocumentUploadFormProps) {
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [dragging, setDragging] = useState(false);
    const [success, setSuccess] = useState<string | null>(null);
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
        resolver: zodResolver(documentUploadSchema),
        defaultValues: {
            name: "",
        },
    });

    const file = watch("file");
    const nameRegister = register("name");

    function assignFile(next: File | undefined) {
        if (next == null) {
            return;
        }
        setSuccess(null);
        setValue("file", next, {shouldValidate: true, shouldTouch: true});
        if (!getValues("name").trim()) {
            setValue("name", fileStem(next.name), {shouldValidate: true});
        }
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
            const accepted = await uploadDocument(data.name, data.file);
            reset({name: ""});
            if (fileInputRef.current) {
                fileInputRef.current.value = "";
            }
            onUploaded?.(accepted);
            setSuccess(
                accepted.converted
                    ? "Document uploaded and converted to .docx."
                    : "Document uploaded.",
            );
        } catch (error) {
            setError("root", {
                message: getApiErrorMessage(error, "Could not upload the document."),
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
                    <FieldLabel htmlFor="document-name">Name</FieldLabel>
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

                <Field data-invalid={!!errors.file || undefined}>
                    <FieldLabel htmlFor="document-file">File</FieldLabel>
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
                        <p className="text-sm">
                            Drop a file here or{" "}
                            <span className="font-medium underline-offset-2">choose one</span>
                        </p>
                        <p className="mt-1 text-sm text-muted-foreground">
                            {file ? file.name : "PDF, Word, Excel, CSV, XML, JSON, Markdown, or ODT. Up to 32 MB."}
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
                {isSubmitting ? "Uploading..." : "Upload"}
            </Button>
        </form>
    );
}
