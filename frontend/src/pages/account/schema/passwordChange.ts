import {z} from "zod";

import type {TranslateFn} from "@/shared/i18n/I18nProvider";

export function createPasswordChangeSchema(t: TranslateFn) {
    return z
        .object({
            current: z.string().min(1, t("validation.passwordRequired")),
            // bcrypt reads at most 72 bytes; Cyrillic letters take 2 each.
            next: z
                .string()
                .min(8, t("validation.passwordMin"))
                .refine((value) => new TextEncoder().encode(value).length <= 72, t("validation.passwordMax")),
            confirm: z.string(),
        })
        .refine((data) => data.confirm === data.next, {path: ["confirm"], message: t("account.passwordsDiffer")})
        .refine((data) => data.next !== data.current, {path: ["next"], message: t("account.passwordSame")});
}

export type PasswordChangeFormData = z.infer<ReturnType<typeof createPasswordChangeSchema>>;
