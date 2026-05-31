import type { MetadataRoute } from "next";

const BASE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://ozpropertyreport.com";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: [
        "/api/",
        "/profile",
        "/my-properties",
        "/sign-in",
        "/sign-up",
        "/credits",
      ],
    },
    sitemap: `${BASE_URL}/sitemap.xml`,
  };
}
