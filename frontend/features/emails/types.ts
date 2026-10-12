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

/** An earlier message carried inside an email's text: reply history or a forward. Offsets are code points into `plain`. */
export interface QuotedBlock {
  startOffset: number;
  endOffset: number;
  kind: "reply" | "forward";
  attribution?: string | null;
  fromName?: string | null;
  fromAddress?: string | null;
  dateSent?: string | null;
}

/** What an email's meaningful hash was computed from. */
export type MeaningfulHashSource = "messageId" | "content";

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
  /** Same for every copy of one message; see `meaningfulHashSource` for how it was matched. */
  meaningfulHash?: string | null;
  meaningfulHashSource?: MeaningfulHashSource | null;
  /** Labels or folders associated with the email */
  labels: string[];
  quotedBlocks?: QuotedBlock[];
}

export interface EmailBase {
  /** Parsed representation of a single RFC 2822 email message. Has no id of its own -- correlate via the source file's id. */
  plain?: string | null;
  html?: string | null;
  metadata: EmailMetadata;
  /** True attachments as the parser found them, not images the body shows; `useEmailAttachments` matches them to stored files. */
  attachments: FileRecord[];
  /** Other email files that are copies of the same message (same meaningful hash), in datasets you can see. */
  copyFileIds?: string[];
}

/** How a conversation's emails were found: by headers alone, or with emails the headers miss linked by quoted text
 * (same subject without Re: / Fwd:, within 30 days, one quotes the other). */
export type ConversationSource = "headers" | "quotedText";

export interface ConversationEmail {
  fileId: string;
  title?: string | null;
  fromName?: string | null;
  fromAddress?: string | null;
  dateSent?: string | null;
  /** Opening of the text this email adds, quoted history excluded. */
  preview: string;
}

/** An email's conversation in date order, copies of one message listed once. */
export interface EmailConversation {
  conversationId?: string | null;
  source: ConversationSource;
  emails: ConversationEmail[];
}
