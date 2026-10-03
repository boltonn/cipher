"use client";

import { UserAccessManager } from "@/features/users/components/user-access-manager";

export default function AdminUsersPage() {
  return (
    <div className="w-full max-w-2xl">
      <p className="mb-4 text-sm text-muted-foreground">
        Choose who is an admin and which datasets each user can access. Admins
        see every dataset.
      </p>
      <UserAccessManager />
    </div>
  );
}
