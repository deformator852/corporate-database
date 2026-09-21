import {z} from "zod";

import {
    DOCUMENT_EXTENSIONS,
    fileExtension,
    MAX_DOCUMENT_BYTES,
} from "@pages/documents/model/documents";

const allowed = new Set<string>(DOCUMENT_EXTENSIONS);

export const documentUploadSchema = z.object({
    name: z
        .string()
        .trim()
        .min(1, "Enter a name")
        .max(200, "Name is too long"),
    file: z
        .instanceof(File, {message: "Choose a file"})
        .refine((file) => file.size > 0, "The file is empty.")
        .refine(
            (file) => file.size <= MAX_DOCUMENT_BYTES,
            "The file is too large.",
        )
        .refine(
            (file) => allowed.has(fileExtension(file.name)),
            "This file type is not supported.",
        ),
});

export type DocumentUploadFormData = z.infer<typeof documentUploadSchema>;
