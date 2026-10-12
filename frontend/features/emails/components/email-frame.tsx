// Copyright (c) 2026 Cloudflare, Inc.
// Licensed under the Apache 2.0 license found in the LICENSE file or at:
//     https://opensource.org/licenses/Apache-2.0
"use client";
import { useTheme } from "@/providers/theme-provider";
import DOMPurify from "dompurify";
import { useMemo } from "react";

// any color the email sets itself: inline `color:` / `background:`, `bgcolor=` / `color=` attributes, `<font color>`
const OWN_COLORS = /\b(?:color|background)(?:-color)?\s*:|\b(?:bg)?color\s*=/i;

interface EmailIframeProps {
  body: string;
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
 *   plain-http tracking pixels. Blocked images just don't render;
 *   the block is silent by design.
 *
 * Page defaults follow the app theme: transparent over the viewer's card, with
 * the browser's scheme-aware system colors (CanvasText, LinkText, GrayText).
 * An email that sets colors of its own was designed against a white page, so it
 * gets one -- its gray text would vanish on dark. Inline styles are never changed.
 */
export default function EmailIframe({ body }: EmailIframeProps) {
  // Rendered as a `srcDoc` prop rather than assigned in an effect: the iframe
  // then enters the DOM with its document already set, as a single navigation.
  // Assigning `iframe.srcdoc` post-mount first commits about:blank and then
  // navigates to the srcdoc, and when that second navigation lands mid
  // dialog-open the compositor can keep showing the stale blank frame -- the
  // document loads but the pane paints white.
  const { resolvedTheme } = useTheme();
  const srcDoc = useMemo(() => {
    if (!body) return undefined;

    const cleanBody = DOMPurify.sanitize(body, {
      USE_PROFILES: { html: true },
      FORBID_TAGS: ["style"],
      ADD_ATTR: ["target"],
      FORCE_BODY: true,
    });

    // Use srcdoc so the iframe is truly sandboxed (no same-origin access).
    // We can't use doc.write() because that requires allow-same-origin.
    const scheme = OWN_COLORS.test(cleanBody) ? "light" : resolvedTheme;
    return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data: cid: https:; script-src 'unsafe-inline';">
<style>
* { box-sizing: border-box; }
html {
	background: ${scheme === "light" && resolvedTheme === "dark" ? "#ffffff" : "transparent"};
	color-scheme: ${scheme};
}
body {
	font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
	font-size: 14px;
	line-height: 1.6;
	color: CanvasText;
	background: transparent;
	padding: 24px;
	margin: 0;
	word-wrap: break-word;
	overflow-wrap: break-word;
}
[style*="position: fixed"], [style*="position:fixed"], [style*="position: absolute"], [style*="position:absolute"] {
	position: relative !important;
}
a { color: LinkText; }
img { max-width: 100%; height: auto; }
blockquote {
	border-left: 3px solid color-mix(in srgb, CanvasText 25%, transparent);
	padding-left: 1em;
	margin-left: 0;
	color: GrayText;
}
pre {
	background: color-mix(in srgb, CanvasText 8%, transparent);
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
  }, [body, resolvedTheme]);

  return (
    <iframe
      srcDoc={srcDoc}
      className="block w-full border-0 h-full"
      sandbox="allow-scripts allow-popups allow-top-navigation-by-user-activation"
      title="Email content"
    />
  );
}
