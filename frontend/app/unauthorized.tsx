import { StatusPage } from "@/components/status-page";

/** API 401s (signed out / session expired), and `unauthorized()` calls. */
export default function Unauthorized() {
  return <StatusPage kind="unauthorized" />;
}
