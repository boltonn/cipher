import { StatusPage } from "@/components/status-page";

/** API 403s on a page's own data, and `forbidden()` calls. */
export default function Forbidden() {
  return <StatusPage kind="forbidden" />;
}
