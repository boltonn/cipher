import { FileRecord } from "@/features/files/types";

export type ParticipantType = "email" | "phone";

export interface Participant {
  name?: string | null;
  type: ParticipantType;
  value: string;
}

export interface EmailAddress extends Omit<Participant, "type"> {
  type: "email";
}

export interface EmailMetadata {
  /** Subject line. */
  title?: string | null;
  /** Sender if email is sent on behalf of someone else. */
  sender?: EmailAddress | null;
  from: EmailAddress;
  to: EmailAddress[];
  cc: EmailAddress[];
  bcc: EmailAddress[];
  dateSent?: Date | string | null;
  conversationId?: string | null;
  messageId?: string | null;
  /** Labels or folders associated with the email */
  labels: string[];
}

export interface EmailBase {
  /** Parsed representation of a single RFC 2822 email message. Has no id of its own -- correlate via the source file's id. */
  plain?: string | null;
  html?: string | null;
  metadata: EmailMetadata;
  attachments: FileRecord[];
  meaningfulHash?: string | null;
}
