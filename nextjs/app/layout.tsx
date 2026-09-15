import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Payment Demo (Omise test mode)",
  description: "Learning payment flow: Next.js + Django + Omise test mode",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="th">
      <body>
        <div className="test-banner">TEST MODE: ไม่มีการตัดเงินจริง</div>
        {children}
      </body>
    </html>
  );
}
