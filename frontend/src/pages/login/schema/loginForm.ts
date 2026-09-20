import {z} from "zod";

export const loginSchema = z.object({
    email: z.email("Enter a valid email address"),
    password: z
        .string()
        .min(1, "Enter your password")
        .min(8, "Password must be at least 8 characters")
        .max(100, "Password is too long"),
});

export type LoginFormData = z.infer<typeof loginSchema>;
