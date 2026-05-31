import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { UserButton } from "@clerk/nextjs";
import Link from "next/link";
import "@/app/globals.css";

export const metadata: Metadata = {
  title: "OZ Property Report Admin Console",
  description: "Property intelligence platform administration",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ClerkProvider
      signInUrl="/sign-in"
      signUpUrl="/sign-up"
      afterSignOutUrl="/sign-in"
    >
      <html lang="en">
        <body className="min-h-screen bg-gray-950 text-gray-100">
          <nav className="bg-gray-900 border-b border-gray-800">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
              <div className="flex justify-between h-16">
                <div className="flex">
                  <div className="flex-shrink-0 flex items-center">
                    <h1 className="text-xl font-bold text-white">
                      OZ Property Report <span className="text-sm text-gray-400">Admin</span>
                    </h1>
                  </div>
                  <div className="ml-10 flex space-x-8">
                    <Link
                      href="/"
                      className="inline-flex items-center px-1 pt-1 text-sm font-medium text-gray-200 border-b-2 border-transparent hover:border-gray-600"
                    >
                      Dashboard
                    </Link>
                    <Link
                      href="/scrape"
                      className="inline-flex items-center px-1 pt-1 text-sm font-medium text-gray-200 border-b-2 border-transparent hover:border-gray-600"
                    >
                      Scrape
                    </Link>
                    <Link
                      href="/properties"
                      className="inline-flex items-center px-1 pt-1 text-sm font-medium text-gray-200 border-b-2 border-transparent hover:border-gray-600"
                    >
                      Properties
                    </Link>
                    <Link
                      href="/users"
                      className="inline-flex items-center px-1 pt-1 text-sm font-medium text-gray-200 border-b-2 border-transparent hover:border-gray-600"
                    >
                      Users
                    </Link>
                    
                  </div>
                </div>
                <div className="flex items-center">
                  <UserButton afterSignOutUrl="/sign-in" />
                </div>
              </div>
            </div>
          </nav>
          <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
            {children}
          </main>
        </body>
      </html>
    </ClerkProvider>
  );
}
