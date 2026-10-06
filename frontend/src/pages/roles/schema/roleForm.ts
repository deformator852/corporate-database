import {z} from "zod";

import type {TranslateFn} from "@/shared/i18n/I18nProvider";
import {keyFromName} from "@/shared/lib/keyFromName";

export function createRoleFormSchema(t: TranslateFn, mode: "create" | "edit") {
    return z
        .object({
            name: z
                .string()
                .trim()
                .min(2, t("validation.roleNameMin"))
                .max(100, t("validation.roleNameMax")),
            description: z.string(),
            permission_keys: z.array(z.string()),
        })
        .superRefine((value, ctx) => {
            if (mode === "edit") {
                return;
            }
            if (keyFromName(value.name) == null) {
                ctx.addIssue({
                    code: "custom",
                    path: ["name"],
                    message: t("validation.roleNameLetter"),
                });
            }
        });
}

export type RoleFormData = z.infer<ReturnType<typeof createRoleFormSchema>>;
