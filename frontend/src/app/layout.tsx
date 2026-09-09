import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AuthHeader, Header } from "@/components/Header";
import "./globals.css";

export const metadata: Metadata = {
  title: "Personal Assistant",
  description: "Your customizable personal assistant — email, monitoring, and automations.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthHeader>
          <Header />
          <main className="mx-auto max-w-5xl px-4 py-10">{children}</main>
        </AuthHeader>
      </body>
    </html>
  );
}
