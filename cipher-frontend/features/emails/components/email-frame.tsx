// Copyright (c) 2026 Cloudflare, Inc.
// Licensed under the Apache 2.0 license found in the LICENSE file or at:
//     https://opensource.org/licenses/Apache-2.0
"use client";
import DOMPurify from "dompurify";
import { useEffect, useRef } from "react";
import { toast } from "sonner";

interface EmailIframeProps {
  body: string;
}

interface CspViolation {
  blockedURI: string;
  directive: string;
}

/** Best-effort hostname for display; falls back to the raw URI if it doesn't parse. */
function hostnameOf(uri: string): string {
  try {
    return new URL(uri).hostname || uri;
  } catch {
    return uri;
  }
}

function notifyBlockedImages(violations: CspViolation[]) {
  const hosts = Array.from(
    new Set(
      violations.filter((v) => v.directive.startsWith("img-src")).map((v) => hostnameOf(v.blockedURI))
    )
  );
  if (hosts.length === 0) return;

  const shown = hosts.slice(0, 5).join(", ");
  const more = hosts.length > 5 ? ` and ${hosts.length - 5} more` : "";

  toast.warning(`Blocked ${hosts.length} image${hosts.length > 1 ? "s" : ""} in this email`, {
    description: `Insecure or unsupported sources: ${shown}${more}`,
    duration: 10_000,
    action: {
      label: "Copy URLs",
      onClick: () => navigator.clipboard.writeText(hosts.join("\n")),
    },
  });
}

/**
 * Renders email HTML inside a sandboxed iframe that fills its parent's
 * height (the caller is expected to give it a sized container) and scrolls
 * internally, rather than trying to measure and report its own content
 * height back to the parent -- that required a postMessage round-trip
 * from inside a cross-origin sandbox, which turned out to race badly
 * against dialog-open transitions and container visibility changes.
 *
 * Security model:
 * - DOMPurify sanitises the HTML before injection.
 * - The iframe sandbox does NOT include `allow-same-origin`, so even if
 *   DOMPurify has a bypass the attacker's code runs in an opaque origin
 *   with no access to the parent page's cookies, DOM, or API.
 * - A strict CSP meta tag blocks external resource loads inside the
 *   iframe as a defense-in-depth layer -- most commonly this blocks
 *   plain-http tracking pixels. Blocked-resource reports from the
 *   iframe's own `securitypolicyviolation` events are relayed to the
 *   parent via `postMessage` and surfaced as a toast, so images being
 *   blocked is visible rather than silent.
 */
export default function EmailIframe({ body }: EmailIframeProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (event.source !== iframeRef.current?.contentWindow) return;
      const data = event.data;
      if (!data || typeof data !== "object") return;

      if (data.__emailIframeCspViolations && Array.isArray(data.violations)) {
        notifyBlockedImages(data.violations);
      }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe || !body) return;

    const cleanBody = DOMPurify.sanitize(body, {
      USE_PROFILES: { html: true },
      FORBID_TAGS: ["style"],
      ADD_ATTR: ["target"],
      FORCE_BODY: true,
    });

    // Use srcdoc so the iframe is truly sandboxed (no same-origin access).
    // We can't use doc.write() because that requires allow-same-origin.
    iframe.srcdoc = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data: cid: https:; script-src 'unsafe-inline';">
<script>
(function () {
	// Registered before any <img> in the body parses, so it catches
	// violations from images that start loading immediately during
	// HTML parsing -- a listener added after the body would miss them.
	var violations = [];
	var timer = null;
	document.addEventListener("securitypolicyviolation", function (e) {
		violations.push({ blockedURI: e.blockedURI, directive: e.violatedDirective });
		if (timer) clearTimeout(timer);
		timer = setTimeout(function () {
			parent.postMessage({ __emailIframeCspViolations: true, violations: violations }, "*");
		}, 300);
	});
})();
<\/script>
<style>
* { box-sizing: border-box; }
html {
	background: #ffffff;
	color-scheme: light;
}
body {
	font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
	font-size: 14px;
	line-height: 1.6;
	color: #1a1a1a;
	background: #ffffff;
	padding: 24px;
	margin: 0;
	word-wrap: break-word;
	overflow-wrap: break-word;
}
[style*="position: fixed"], [style*="position:fixed"], [style*="position: absolute"], [style*="position:absolute"] {
	position: relative !important;
}
a { color: #2563eb; }
img { max-width: 100%; height: auto; }
blockquote {
	border-left: 3px solid #d1d5db;
	padding-left: 1em;
	margin-left: 0;
	color: #6b7280;
}
pre {
	background: #f3f4f6;
	padding: 12px;
	border-radius: 6px;
	overflow-x: auto;
	font-size: 13px;
}
table { border-collapse: collapse; max-width: 100%; }
td, th { padding: 4px 8px; }
p { margin: 4px 0; }
h1, h2, h3 { margin: 8px 0 4px; }
ul, ol { padding-left: 20px; margin: 4px 0; }
</style>
</head>
<body>${cleanBody}</body>
</html>`;
  }, [body]);

  return (
    <iframe
      ref={iframeRef}
      className="block w-full border-0 h-full"
      sandbox="allow-scripts allow-popups allow-top-navigation-by-user-activation"
      title="Email content"
    />
  );
}
