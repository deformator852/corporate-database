import {z} from "zod";

import {keyFromName} from "@/shared/lib/keyFromName";

export function roleFormSchema(mode: "create" | "edit") {
    return z
        .object({
            name: z
                .string()
                .trim()
                .min(2, "Enter at least 2 characters")
                .max(100, "Must be 100 characters or fewer"),
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
                    message: "Name must start with a letter",
                });
            }
        });
}

export type RoleFormData = z.infer<ReturnType<typeof roleFormSchema>>;
