import { FileRecord } from "@/features/files/types";

export interface EmailParticipant {
  name?: string | null;
  type: "email" | "phone";
  value: string;
}

export interface EmailMetadata {
  /** Subject line. */
  title?: string | null;
  /** Sender if email is sent on behalf of someone else. */
  sender?: EmailParticipant | null;
  from: EmailParticipant;
  to: EmailParticipant[];
  cc: EmailParticipant[];
  bcc: EmailParticipant[];
  dateSent?: Date | string | null;
  conversationId?: string | null;
  messageId?: string | null;
  /** Labels or folders associated with the email */
  labels: string[];
}

export interface EmailBase {
  /** Parsed representation of a single RFC 2822 email message. */
  id: string;
  plain?: string | null;
  html?: string | null;
  metadata: EmailMetadata;
  attachments: FileRecord[];
  meaningfulHash?: string | null;
}
