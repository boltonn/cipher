import { StatusPage } from "@/components/status-page";

/** Unknown URLs, API 404s on a page's own data, and `notFound()` calls. */
export default function NotFound() {
  return <StatusPage kind="notFound" />;
}
