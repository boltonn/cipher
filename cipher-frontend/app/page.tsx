import { Example, ExampleWrapper } from "@/components/example";

export default function Page() {
  return (
    <ExampleWrapper>
      <Example title="Welcome to Cipher">
        <p className="text-sm text-muted-foreground">
          Use the sidebar to explore messages, images, emails, datasets, and
          chat.
        </p>
      </Example>
    </ExampleWrapper>
  );
}
