import { z } from "zod";

const PASSWORD_MIN = 8;
const PASSWORD_MAX = 128;

export const loginSchema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
});

export type LoginInput = z.infer<typeof loginSchema>;

export const registerSchema = z
  .object({
    username: z
      .string()
      .min(3, "Username must be at least 3 characters.")
      .max(64, "Username must be 64 characters or fewer.")
      .regex(/^[A-Za-z0-9_.-]+$/, "Username may only contain letters, digits, '.', '-' and '_'."),
    email: z.string().email("Enter a valid email address."),
    password: z
      .string()
      .min(PASSWORD_MIN, `Password must be at least ${PASSWORD_MIN} characters.`)
      .max(PASSWORD_MAX, `Password must be ${PASSWORD_MAX} characters or fewer.`),
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match.",
    path: ["confirmPassword"],
  });

export type RegisterInput = z.infer<typeof registerSchema>;
