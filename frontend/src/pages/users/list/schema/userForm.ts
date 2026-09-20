import {z} from "zod";

const nameSchema = z
    .string()
    .trim()
    .min(2, "Enter at least 2 characters")
    .max(100, "Must be 100 characters or fewer");

const passwordSchema = z
    .string()
    .min(8, "Password must be at least 8 characters")
    .max(100, "Password is too long");

export const userFormSchema = z
    .object({
        first_name: nameSchema,
        last_name: nameSchema,
        email: z.email("Enter a valid email address"),
        password: z.string(),
        role_keys: z.array(z.string()),
    })
    .superRefine((value, ctx) => {
        if (value.password.length === 0) {
            return;
        }
        const parsed = passwordSchema.safeParse(value.password);
        if (!parsed.success) {
            for (const issue of parsed.error.issues) {
                ctx.addIssue({...issue, path: ["password"]});
            }
        }
    });

export type UserFormData = z.infer<typeof userFormSchema>;

export function createUserFormSchema(mode: "create" | "edit") {
    return userFormSchema.superRefine((value, ctx) => {
        if (mode === "create" && value.password.length === 0) {
            ctx.addIssue({
                code: "custom",
                path: ["password"],
                message: "Enter a password",
            });
        }
    });
}
