import {z} from "zod";

import type {TranslateFn} from "@/shared/i18n/I18nProvider";

export function createUserFormSchema(t: TranslateFn, mode: "create" | "edit") {
    const nameSchema = z
        .string()
        .trim()
        .min(2, t("validation.userNameMin"))
        .max(100, t("validation.roleNameMax"));

    // bcrypt reads at most 72 bytes; Cyrillic letters take 2 each.
    const passwordSchema = z
        .string()
        .min(8, t("validation.passwordMin"))
        .refine(
            (value) => new TextEncoder().encode(value).length <= 72,
            t("validation.passwordMax"),
        );

    return z
        .object({
            first_name: nameSchema,
            last_name: nameSchema,
            email: z.email(t("validation.email")),
            password: z.string(),
            role_keys: z.array(z.string()),
        })
        .superRefine((value, ctx) => {
            if (value.password.length === 0) {
                if (mode === "create") {
                    ctx.addIssue({
                        code: "custom",
                        path: ["password"],
                        message: t("validation.passwordEnter"),
                    });
                }
                return;
            }
            const parsed = passwordSchema.safeParse(value.password);
            if (!parsed.success) {
                for (const issue of parsed.error.issues) {
                    ctx.addIssue({...issue, path: ["password"]});
                }
            }
        });
}

export type UserFormData = z.infer<ReturnType<typeof createUserFormSchema>>;
