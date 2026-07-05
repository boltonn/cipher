import { FileRecord } from "@/features/files/types";

export interface EmailAddress {
  name?: string | null;
  address: string;
}

export interface EmailMetadata {
  /** Sender if email is sent on behalf of someone else. */
  sender?: EmailAddress | null;
  from: EmailAddress;
  to: EmailAddress[];
  cc: EmailAddress[];
  bcc: EmailAddress[];
  subject?: string | null; // serialization_alias for subject
  dateSent?: Date | string | null;
  conversationId?: string | null;
  messageId?: string | null;
  /** Labels or folders associated with the email */
  labels: string[];
}

export interface EmailBase {
  /** Parsed representation of a single RFC 2822 email message. */
  id: string;
  text?: string | null;
  html?: string | null;
  metadata: EmailMetadata;
  attachments: FileRecord[];
  meaningfulHash?: string | null;
}
