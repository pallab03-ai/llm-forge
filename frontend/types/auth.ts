export type UserRole = "user" | "admin";

export type AuthUser = {
  id: string;
  email: string;
  username: string;
  role: UserRole;
};

export type AuthToken = {
  accessToken: string;
  tokenType: "bearer";
  expiresAt: number;
};
