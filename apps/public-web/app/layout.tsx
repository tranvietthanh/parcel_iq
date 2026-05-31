import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Link from "next/link";
import { ClerkProvider } from "@clerk/nextjs";
import { AfterSignInClaimEffect } from "@/components/auth/AfterSignInClaimEffect";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "OZ Property Report — Property Intelligence for Investors",
  description:
    "Aggregated property data, risk analysis, and investment insights for Australian real estate.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <ClerkProvider
      publishableKey={process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY}
      signInUrl="/sign-in"
      signUpUrl="/sign-up"
      signInFallbackRedirectUrl="/"
      signUpFallbackRedirectUrl="/"
    >
      <html lang="en">
        <body className={`${inter.variable} font-sans antialiased`}>
          <AfterSignInClaimEffect />
          {children}
          <footer className="fixed bottom-0 left-0 right-0 z-50 bg-white/90 px-4 py-2 text-center text-xs text-zinc-500 backdrop-blur dark:bg-zinc-900/90 dark:text-zinc-400">
            <strong>General Information Only.</strong> OZ Property Report provides
            aggregated data for informational purposes only. It does not
            constitute financial, legal, or investment advice. Always seek
            independent professional advice before making investment decisions.
            <span className="mx-1">·</span>
            <Link href="/terms-of-service" className="underline underline-offset-2 hover:text-zinc-900 dark:hover:text-white transition-colors">Terms of Service</Link>
            <span className="mx-1">·</span>
            <Link href="/privacy-policy" className="underline underline-offset-2 hover:text-zinc-900 dark:hover:text-white transition-colors">Privacy Policy</Link>
          </footer>
        </body>
      </html>
    </ClerkProvider>
  );
}
