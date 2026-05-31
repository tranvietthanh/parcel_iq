import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Terms of Service — OZ Property Report",
  description:
    "Terms and conditions governing the use of OZ Property Report, including acceptable use, credits, liability, and intellectual property.",
};

const LAST_UPDATED = "29 May 2026";

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mt-10 mb-4 text-xl font-semibold tracking-tight text-zinc-900 dark:text-white">
      {children}
    </h2>
  );
}

function SubHeading({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="mt-6 mb-2 text-base font-semibold text-zinc-800 dark:text-zinc-200">
      {children}
    </h3>
  );
}

function Paragraph({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-4 leading-relaxed text-zinc-700 dark:text-zinc-300">
      {children}
    </p>
  );
}

function BulletList({ children }: { children: React.ReactNode }) {
  return (
    <ul className="mb-4 ml-6 list-disc space-y-2 text-zinc-700 dark:text-zinc-300 [&>li]:leading-relaxed">
      {children}
    </ul>
  );
}

export default function TermsOfServicePage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-16 pb-20">
      {/* Back nav */}
      <div className="mb-6">
        <Link
          href="/"
          id="tos-back-link"
          className="inline-flex items-center text-sm font-medium text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
        >
          ← Back to Map
        </Link>
      </div>

      {/* Header */}
      <div className="mb-10">
        <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
          Terms of Service
        </h1>
        <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
          Last updated: {LAST_UPDATED}
        </p>
      </div>

      {/* Content */}
      <article>
        <SectionHeading>1. Acceptance of Terms</SectionHeading>
        <Paragraph>
          By accessing or using OZ Property Report (&ldquo;the Service&rdquo;), you agree
          to be bound by these Terms of Service (&ldquo;Terms&rdquo;). If you do not agree
          with any part of these Terms, you must not access or use the Service.
        </Paragraph>
        <Paragraph>
          We may update these Terms from time to time. Continued use of the
          Service after changes constitutes acceptance of the revised Terms.
        </Paragraph>

        <SectionHeading>2. Description of Service</SectionHeading>
        <Paragraph>
          OZ Property Report is a property intelligence platform that provides
          aggregated property data, risk analysis, and investment insights for
          Australian real estate. The Service includes interactive maps,
          property reports, and suburb-level analytics.
        </Paragraph>

        <SectionHeading>3. User Accounts</SectionHeading>
        <Paragraph>
          To access certain features, you may be required to create an account
          via our authentication provider (Clerk). You are responsible for:
        </Paragraph>
        <BulletList>
          <li>Maintaining the confidentiality of your account credentials</li>
          <li>All activities that occur under your account</li>
          <li>Providing accurate and current information during registration</li>
          <li>Notifying us promptly of any unauthorised use of your account</li>
        </BulletList>

        <SectionHeading>4. Credits and Payments</SectionHeading>
        <SubHeading>4.1 Free Daily Credits</SubHeading>
        <Paragraph>
          Registered users receive a number of free credits each day. Daily
          free credits reset at midnight AEST and do not roll over to
          subsequent days.
        </Paragraph>
        <SubHeading>4.2 Purchased Credits</SubHeading>
        <Paragraph>
          Users may purchase additional credits through our secure checkout
          (powered by Stripe). Purchased credits never expire but are
          non-refundable once the transaction is complete.
        </Paragraph>
        <SubHeading>4.3 Pricing</SubHeading>
        <Paragraph>
          All prices are displayed in Australian Dollars (AUD). We reserve the
          right to change pricing at any time with reasonable notice.
        </Paragraph>

        <SectionHeading>5. Acceptable Use</SectionHeading>
        <Paragraph>You agree not to:</Paragraph>
        <BulletList>
          <li>
            Use the Service for any unlawful purpose or in violation of any
            applicable laws
          </li>
          <li>
            Scrape, crawl, or use automated means to extract data from the
            Service without prior written consent
          </li>
          <li>
            Attempt to interfere with, compromise, or disrupt the Service or
            its infrastructure
          </li>
          <li>
            Redistribute, resell, or sublicence any data or reports obtained
            through the Service without authorisation
          </li>
          <li>
            Impersonate another person or entity, or misrepresent your
            affiliation with any party
          </li>
        </BulletList>

        <SectionHeading>6. Intellectual Property</SectionHeading>
        <Paragraph>
          All content, data compilations, graphics, logos, and software
          provided through the Service are the property of OZ Property Report
          or its licensors and are protected by Australian and international
          intellectual property laws.
        </Paragraph>
        <Paragraph>
          Property reports generated for you are licensed for your personal,
          non-commercial use only. You may not reproduce, distribute, or
          publicly display reports without our written permission.
        </Paragraph>

        <SectionHeading>7. Data Sources and Accuracy</SectionHeading>
        <Paragraph>
          The Service aggregates data from publicly available government
          databases, third-party providers, and other sources. While we
          endeavour to ensure accuracy, we make no guarantees regarding the
          completeness, reliability, or timeliness of any data.
        </Paragraph>
        <Paragraph>
          Property data, risk assessments, and investment insights are
          provided for general informational purposes only and should not be
          relied upon as the sole basis for any financial, legal, or
          investment decisions.
        </Paragraph>

        <SectionHeading>8. Disclaimer of Warranties</SectionHeading>
        <Paragraph>
          The Service is provided on an &ldquo;as is&rdquo; and &ldquo;as available&rdquo; basis
          without warranties of any kind, whether express or implied,
          including but not limited to implied warranties of merchantability,
          fitness for a particular purpose, and non-infringement.
        </Paragraph>

        <SectionHeading>9. Limitation of Liability</SectionHeading>
        <Paragraph>
          To the maximum extent permitted by Australian law, OZ Property
          Report shall not be liable for any indirect, incidental, special,
          consequential, or punitive damages, or any loss of profits or
          revenue, whether incurred directly or indirectly, arising from:
        </Paragraph>
        <BulletList>
          <li>Your use of or inability to use the Service</li>
          <li>Errors, inaccuracies, or omissions in any data or reports</li>
          <li>
            Any investment or financial decisions made based on information
            from the Service
          </li>
          <li>Unauthorised access to your account or data</li>
        </BulletList>

        <SectionHeading>10. Termination</SectionHeading>
        <Paragraph>
          We reserve the right to suspend or terminate your account and access
          to the Service at our discretion, without prior notice, for conduct
          that violates these Terms or is otherwise harmful to other users or
          the Service.
        </Paragraph>

        <SectionHeading>11. Governing Law</SectionHeading>
        <Paragraph>
          These Terms are governed by and construed in accordance with the
          laws of the State of New South Wales, Australia. Any disputes
          arising from or relating to these Terms shall be subject to the
          exclusive jurisdiction of the courts of New South Wales.
        </Paragraph>

        <SectionHeading>12. Contact</SectionHeading>
        <Paragraph>
          If you have any questions about these Terms, please contact us at{" "}
          <a
            href="mailto:support@ozpropertyreport.com.au"
            className="text-indigo-600 underline underline-offset-2 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
          >
            support@ozpropertyreport.com.au
          </a>
          .
        </Paragraph>
      </article>

      {/* Related link */}
      <div className="mt-12 rounded-xl border border-zinc-200 bg-zinc-50 px-6 py-4 dark:border-zinc-800 dark:bg-zinc-900">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          See also our{" "}
          <Link
            href="/privacy-policy"
            className="font-medium text-indigo-600 underline underline-offset-2 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
          >
            Privacy Policy
          </Link>{" "}
          for information about how we collect, use, and protect your data.
        </p>
      </div>
    </main>
  );
}
