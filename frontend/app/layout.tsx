import { AppSidebar } from "@/components/app-sidebar";
import { PageHeaderProvider } from "@/components/page-header";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ReactQueryProvider } from "@/providers/react-query-provider";
import { THEME_INIT_SCRIPT, ThemeProvider } from "@/providers/theme-provider";
import type { Metadata } from "next";
import { Geist, Geist_Mono, Inter } from "next/font/google";
import Script from "next/script";
import { MotionConfig } from "motion/react";
import { Toaster } from "sonner";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });
const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Cipher",
  description: "Searching unstructured data made easy.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <head>
        {/* Applies the stored theme to <html> before first paint (no flash).
            next/script injects it outside React's tree -- a raw <script> here
            is still reconciled on the client and trips React 19's warning. */}
        <Script id="theme-init" strategy="beforeInteractive">
          {THEME_INIT_SCRIPT}
        </Script>
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased
        bg-background text-foreground overflow-hidden h-screen w-screen flex`}
      >
        {/* Background Indigo Glows */}
        <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden">
          {/* Top Left Glow - Using Indigo 600 */}
          <div
            className="absolute top-[-10%] left-[-10%] w-150 h-150 
            rounded-full bg-primary/15 blur-[120px] animate-slow-pulse"
          ></div>

          {/* Bottom Right Glow - Using Indigo 500 */}
          <div
            className="absolute bottom-[-10%] right-[-10%] w-125 h-125 
            rounded-full bg-primary/10 blur-[100px] animate-slow-pulse [animation-delay:2s]"
          ></div>
        </div>

        <MotionConfig reducedMotion="user">
        <ThemeProvider defaultTheme="dark">
          <TooltipProvider>
            <ReactQueryProvider>
              <SidebarProvider>
                <AppSidebar />
                <PageHeaderProvider>
                  <SidebarInset id="main-content" className="h-screen overflow-hidden">
                    {children}
                  </SidebarInset>
                </PageHeaderProvider>
              </SidebarProvider>
            </ReactQueryProvider>
          </TooltipProvider>
          <Toaster theme="dark" richColors closeButton />
        </ThemeProvider>
        </MotionConfig>
      </body>
    </html>
  );
}
