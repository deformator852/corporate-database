import {z} from "zod";

import {
    DOCUMENT_CLASSIFICATIONS,
    DOCUMENT_EXTENSIONS,
    fileExtension,
    MAX_DOCUMENT_BYTES,
} from "@pages/documents/model/documents";
import type {TranslateFn} from "@/shared/i18n/I18nProvider";

const allowed = new Set<string>(DOCUMENT_EXTENSIONS);

export function createDocumentUploadSchema(t: TranslateFn) {
    return z.object({
        name: z
            .string()
            .trim()
            .min(1, t("validation.enterName"))
            .max(200, t("validation.nameTooLong")),
        classification: z.enum(DOCUMENT_CLASSIFICATIONS),
        file: z
            .instanceof(File, {message: t("validation.chooseFile")})
            .refine((file) => file.size > 0, t("validation.fileEmpty"))
            .refine(
                (file) => file.size <= MAX_DOCUMENT_BYTES,
                t("validation.fileTooLarge"),
            )
            .refine(
                (file) => allowed.has(fileExtension(file.name)),
                t("validation.fileTypeUnsupported"),
            ),
    });
}

export type DocumentUploadFormData = z.infer<
    ReturnType<typeof createDocumentUploadSchema>
>;
