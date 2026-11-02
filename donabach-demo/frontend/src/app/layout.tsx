import type { Metadata } from "next";
import { PortalProvider } from "@/lib/portal-state";
import { Shell } from "@/components/shell/Shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Waramoug",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>
        <PortalProvider>
          <Shell>{children}</Shell>
        </PortalProvider>
      </body>
    </html>
  );
}
