import {z} from "zod";

import {DOCUMENT_CLASSIFICATIONS} from "@/entities/document/model";
import type {TranslateFn} from "@/shared/i18n/I18nProvider";

export function createDocumentEditSchema(t: TranslateFn) {
    return z.object({
        name: z.string().trim().min(1, t("validation.enterName")).max(200, t("validation.nameTooLong")),
        classification: z.enum(DOCUMENT_CLASSIFICATIONS),
    });
}

export type DocumentEditFormData = z.infer<ReturnType<typeof createDocumentEditSchema>>;
