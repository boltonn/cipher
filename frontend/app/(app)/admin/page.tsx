import { NAV } from "@/lib/nav";
import { redirect } from "next/navigation";

export default function AdminPage() {
  redirect(NAV.adminPages[0].url);
}
