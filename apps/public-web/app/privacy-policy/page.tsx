import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy Policy — OZ Property Report",
  description:
    "How OZ Property Report collects, uses, stores, and protects your personal information in accordance with Australian privacy law.",
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

export default function PrivacyPolicyPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-16 pb-20">
      {/* Back nav */}
      <div className="mb-6">
        <Link
          href="/"
          id="privacy-back-link"
          className="inline-flex items-center text-sm font-medium text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
        >
          ← Back to Map
        </Link>
      </div>

      {/* Header */}
      <div className="mb-10">
        <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
          Privacy Policy
        </h1>
        <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
          Last updated: {LAST_UPDATED}
        </p>
      </div>

      {/* Content */}
      <article>
        <SectionHeading>1. Overview</SectionHeading>
        <Paragraph>
          OZ Property Report (&ldquo;we&rdquo;, &ldquo;us&rdquo;, &ldquo;our&rdquo;) is committed to
          protecting your privacy. This Privacy Policy explains how we
          collect, use, disclose, and safeguard your personal information in
          accordance with the{" "}
          <em>Privacy Act 1988</em> (Cth) and the Australian Privacy
          Principles (APPs).
        </Paragraph>
        <Paragraph>
          By using our Service, you consent to the practices described in this
          Privacy Policy.
        </Paragraph>

        <SectionHeading>2. Information We Collect</SectionHeading>
        <SubHeading>2.1 Information You Provide</SubHeading>
        <BulletList>
          <li>
            <strong className="text-zinc-900 dark:text-zinc-100">Account information</strong> — when you sign up, we
            receive your name and email address from our authentication
            provider (Clerk)
          </li>
          <li>
            <strong className="text-zinc-900 dark:text-zinc-100">Payment information</strong> — credit card and billing
            details are processed directly by Stripe and are never stored on
            our servers
          </li>
          <li>
            <strong className="text-zinc-900 dark:text-zinc-100">Support enquiries</strong> — any information you include
            when contacting us
          </li>
        </BulletList>

        <SubHeading>2.2 Information Collected Automatically</SubHeading>
        <BulletList>
          <li>
            <strong className="text-zinc-900 dark:text-zinc-100">Usage data</strong> — pages visited, features used, search
            queries, and property reports downloaded
          </li>
          <li>
            <strong className="text-zinc-900 dark:text-zinc-100">Device information</strong> — browser type, operating
            system, screen resolution, and language preferences
          </li>
          <li>
            <strong className="text-zinc-900 dark:text-zinc-100">Log data</strong> — IP address, access timestamps, and
            referral URLs
          </li>
        </BulletList>

        <SubHeading>2.3 Cookies and Similar Technologies</SubHeading>
        <Paragraph>
          We use essential cookies for authentication and session management.
          We may also use analytics cookies to understand how you interact
          with the Service. You can control cookie preferences through your
          browser settings.
        </Paragraph>

        <SectionHeading>3. How We Use Your Information</SectionHeading>
        <Paragraph>We use the information we collect to:</Paragraph>
        <BulletList>
          <li>Provide, maintain, and improve the Service</li>
          <li>Process credit purchases and manage your account</li>
          <li>Generate and deliver property reports and analytics</li>
          <li>
            Communicate with you about your account, including service
            updates and security alerts
          </li>
          <li>
            Detect, prevent, and address technical issues and security
            threats
          </li>
          <li>
            Comply with legal obligations and enforce our Terms of Service
          </li>
        </BulletList>

        <SectionHeading>4. How We Share Your Information</SectionHeading>
        <Paragraph>
          We do not sell, rent, or trade your personal information. We may
          share your information with:
        </Paragraph>
        <BulletList>
          <li>
            <strong className="text-zinc-900 dark:text-zinc-100">Service providers</strong> — trusted third parties that
            help us operate the Service, including Clerk (authentication),
            Stripe (payments), and cloud hosting providers
          </li>
          <li>
            <strong className="text-zinc-900 dark:text-zinc-100">Legal requirements</strong> — when required by law, court
            order, or government request
          </li>
          <li>
            <strong className="text-zinc-900 dark:text-zinc-100">Business transfers</strong> — in connection with a merger,
            acquisition, or sale of assets, subject to the same privacy
            protections
          </li>
        </BulletList>

        <SectionHeading>5. Data Storage and Security</SectionHeading>
        <Paragraph>
          Your data is stored on secure servers located in Australia. We
          implement industry-standard security measures including:
        </Paragraph>
        <BulletList>
          <li>Encryption of data in transit (TLS) and at rest</li>
          <li>Network-level isolation of internal services and databases</li>
          <li>Regular security audits and vulnerability assessments</li>
          <li>Role-based access controls for internal personnel</li>
        </BulletList>
        <Paragraph>
          While we take reasonable steps to protect your information, no
          method of transmission or storage is 100% secure. We cannot
          guarantee absolute security.
        </Paragraph>

        <SectionHeading>6. Data Retention</SectionHeading>
        <Paragraph>
          We retain your personal information for as long as your account is
          active or as needed to provide you with the Service. If you request
          account deletion, we will remove your personal information within 30
          days, except where retention is required for legal or legitimate
          business purposes.
        </Paragraph>
        <Paragraph>
          Anonymised and aggregated data that cannot identify you may be
          retained indefinitely for analytics and service improvement.
        </Paragraph>

        <SectionHeading>7. Your Rights</SectionHeading>
        <Paragraph>
          Under the Australian Privacy Principles, you have the right to:
        </Paragraph>
        <BulletList>
          <li>
            <strong className="text-zinc-900 dark:text-zinc-100">Access</strong> your personal information held by us
          </li>
          <li>
            <strong className="text-zinc-900 dark:text-zinc-100">Correct</strong> inaccurate or outdated personal
            information
          </li>
          <li>
            <strong className="text-zinc-900 dark:text-zinc-100">Request deletion</strong> of your personal information,
            subject to legal obligations
          </li>
          <li>
            <strong className="text-zinc-900 dark:text-zinc-100">Opt out</strong> of non-essential communications
          </li>
          <li>
            <strong className="text-zinc-900 dark:text-zinc-100">Complain</strong> to the Office of the Australian
            Information Commissioner (OAIC) if you believe your privacy rights
            have been breached
          </li>
        </BulletList>
        <Paragraph>
          To exercise any of these rights, contact us at the address below.
        </Paragraph>

        <SectionHeading>8. Third-Party Links</SectionHeading>
        <Paragraph>
          The Service may contain links to third-party websites or services.
          We are not responsible for the privacy practices of those third
          parties. We encourage you to review their privacy policies before
          providing any personal information.
        </Paragraph>

        <SectionHeading>9. Children&apos;s Privacy</SectionHeading>
        <Paragraph>
          The Service is not intended for users under the age of 18. We do not
          knowingly collect personal information from children. If we become
          aware that a child has provided personal information, we will take
          steps to delete it promptly.
        </Paragraph>

        <SectionHeading>10. Changes to This Policy</SectionHeading>
        <Paragraph>
          We may update this Privacy Policy from time to time. We will notify
          you of significant changes by posting a notice on the Service or
          sending an email to your registered address. Your continued use of
          the Service after any changes constitutes acceptance of the revised
          policy.
        </Paragraph>

        <SectionHeading>11. Contact Us</SectionHeading>
        <Paragraph>
          If you have questions, concerns, or requests regarding this Privacy
          Policy or your personal information, please contact us at:
        </Paragraph>
        <Paragraph>
          <a
            href="mailto:privacy@ozpropertyreport.com.au"
            className="text-indigo-600 underline underline-offset-2 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
          >
            privacy@ozpropertyreport.com.au
          </a>
        </Paragraph>
      </article>

      {/* Related link */}
      <div className="mt-12 rounded-xl border border-zinc-200 bg-zinc-50 px-6 py-4 dark:border-zinc-800 dark:bg-zinc-900">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          See also our{" "}
          <Link
            href="/terms-of-service"
            className="font-medium text-indigo-600 underline underline-offset-2 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
          >
            Terms of Service
          </Link>{" "}
          for the full terms and conditions governing use of OZ Property Report.
        </p>
      </div>
    </main>
  );
}
