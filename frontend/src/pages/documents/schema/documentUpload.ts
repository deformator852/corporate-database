import {z} from "zod";

import {
    DOCUMENT_CLASSIFICATIONS,
    DOCUMENT_EXTENSIONS,
    fileExtension,
    MAX_DOCUMENT_BYTES,
    MAX_UPLOAD_FILES,
} from "@pages/documents/model/documents";
import type {TranslateFn} from "@/shared/i18n/I18nProvider";

const allowed = new Set<string>(DOCUMENT_EXTENSIONS);

export function createDocumentUploadSchema(t: TranslateFn) {
    const file = z
        .instanceof(File)
        .refine((value) => value.size > 0, t("validation.fileEmpty"))
        .refine(
            (value) => value.size <= MAX_DOCUMENT_BYTES,
            t("validation.fileTooLarge"),
        )
        .refine(
            (value) => allowed.has(fileExtension(value.name)),
            t("validation.fileTypeUnsupported"),
        );
    return z
        .object({
            // Typed for a single file; several files are named after themselves.
            name: z.string().trim().max(200, t("validation.nameTooLong")),
            classification: z.enum(DOCUMENT_CLASSIFICATIONS),
            files: z
                .array(file)
                .min(1, t("validation.chooseFile"))
                .max(MAX_UPLOAD_FILES, t("validation.tooManyFiles", {count: MAX_UPLOAD_FILES})),
        })
        .refine((data) => data.files.length !== 1 || data.name.length > 0, {
            path: ["name"],
            message: t("validation.enterName"),
        });
}

export type DocumentUploadFormData = z.infer<
    ReturnType<typeof createDocumentUploadSchema>
>;
