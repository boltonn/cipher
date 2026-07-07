import EmailIframe from "@/features/emails/components/email-frame";
import rawData from "@/features/emails/data/example.json";
import { EmailBase } from "@/features/emails/types";

// Cast the imported JSON to your interface
const email = rawData as EmailBase;

export default function Page() {
  return (
    <div style={{ width: "100%", height: "100vh" }}>
      <EmailIframe body={email.html || ""} />
    </div>
  );
}
