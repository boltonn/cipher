import { useFileChildren } from "@/features/files/api";
import type { FileRecord } from "@/features/files/types";
import type { EmailBase } from "../types";

/** The email's true attachments as stored files, in the email's order -- not every child file:
 * images its body shows can be stored as children too. */
export function useEmailAttachments(
  fileId: string | undefined,
  email: EmailBase | undefined
): FileRecord[] {
  const { data: children = [] } = useFileChildren(email?.attachments.length ? fileId : undefined);
  if (!email) return [];
  const unmatched = [...children];
  return email.attachments.flatMap((attachment) => {
    const sameBytes = (child: FileRecord) => child.sha256 === attachment.sha256;
    const exact = unmatched.findIndex(
      (child) => sameBytes(child) && child.filename === attachment.filename
    );
    const index = exact >= 0 ? exact : unmatched.findIndex(sameBytes);
    return index >= 0 ? unmatched.splice(index, 1) : [];
  });
}
