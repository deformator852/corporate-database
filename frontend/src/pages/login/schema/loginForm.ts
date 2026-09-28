import {z} from "zod";

import type {TranslateFn} from "@/shared/i18n/I18nProvider";

export function createLoginSchema(t: TranslateFn) {
    return z.object({
        email: z.email(t("validation.email")),
        password: z
            .string()
            .min(1, t("validation.passwordRequired"))
            .min(8, t("validation.passwordMin"))
            .max(100, t("validation.passwordMax")),
    });
}

export type LoginFormData = z.infer<ReturnType<typeof createLoginSchema>>;
