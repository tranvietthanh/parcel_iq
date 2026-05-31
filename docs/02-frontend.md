# OZ Property Report – Public Frontend Specification

## 1. Overview

**Application:** `apps/public-web`  
**Technology:** Next.js 15 (App Router), TypeScript, Tailwind CSS, Mapbox GL JS, Clerk  
**URL:** `ozpropertyreport.com`  
**Auth:** Clerk Public Instance — Email/password + Google OAuth  
**Scope:** Investor-facing only. Contains zero admin functionality.

---

## 2. Project Structure

```
/apps/public-web
├── app/
│   ├── (map)/
│   │   ├── layout.tsx             # Full-screen map layout (no header/footer)
│   │   └── page.tsx               # Main map page — entry point
│   ├── property/[id]/
│   │   └── page.tsx               # SSR property permalink (SEO)
│   ├── sign-in/[[...sign-in]]/
│   │   └── page.tsx               # Clerk-hosted sign-in page
│   ├── sign-up/[[...sign-up]]/
│   │   └── page.tsx               # Clerk-hosted sign-up page
│   ├── api/
│   │   └── webhooks/
│   │       └── clerk/route.ts     # Clerk webhook: sync user to DB on creation
│   ├── layout.tsx                 # Root layout — wraps with <ClerkProvider>
│   └── globals.css
├── components/
│   ├── map/
│   │   ├── MapContainer.tsx       # Mapbox GL JS wrapper (client component)
│   │   ├── PropertyMarker.tsx     # Pin on map
│   │   ├── ZoneLayer.tsx          # Polygon overlays (school zones, LGAs)
│   │   └── SearchOmnibox.tsx      # Address/LGA/school omnibox
│   ├── property/
│   │   └── PropertyDetail.tsx     # Unified detail panel/page component
│   ├── auth/
│   │   └── AuthGuard.tsx          # Wraps content that requires sign-in
│   ├── tracking/
│   │   └── DownloadButton.tsx     # Full report download trigger
│   └── ui/
│       ├── Button.tsx
│       ├── Spinner.tsx
│       └── Toast.tsx
├── hooks/
│   ├── useMapBounds.ts            # Debounced map viewport bbox
│   ├── usePropertySearch.ts       # SWR hook → GET /api/search
│   └── useProperty.ts             # SWR hook → GET /api/properties/:id/detail
├── lib/
│   ├── api.ts                     # Typed fetch wrapper (Clerk token attach)
│   └── mapbox.ts                  # Mapbox init helpers
├── types/
│   └── index.ts
├── middleware.ts                  # Clerk auth middleware
├── Dockerfile
└── next.config.ts
```

---

## 3. Clerk Integration

### Provider Setup (`app/layout.tsx`)

```typescript
import { ClerkProvider } from '@clerk/nextjs';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider
      publishableKey={process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY}
      signInUrl="/sign-in"
      signUpUrl="/sign-up"
      afterSignInUrl="/"
      afterSignUpUrl="/"
    >
      <html lang="en">
        <body>{children}</body>
      </html>
    </ClerkProvider>
  );
}
```

### Sign-In / Sign-Up Pages

Clerk provides drop-in components. These pages are thin wrappers only:

```typescript
// app/sign-in/[[...sign-in]]/page.tsx
import { SignIn } from '@clerk/nextjs';

export default function SignInPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <SignIn />
    </div>
  );
}
// Clerk renders: email/password form + "Continue with Google" button
// No custom auth logic needed here
```

### Middleware (`middleware.ts`)

```typescript
import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server';

// Routes that require authentication
const isProtectedRoute = createRouteMatcher([
  '/property/(.*)',    // property detail pages
]);

export default clerkMiddleware((auth, req) => {
  if (isProtectedRoute(req)) {
    auth().protect();  // redirect to sign-in if not authenticated
  }
  // All other routes (map, search) are public — no auth required
});

export const config = {
  matcher: ['/((?!_next|.*\\..*).*)'],
};
```

### API Client — Attaching Clerk Token (`lib/api.ts`)

```typescript
import { useAuth } from '@clerk/nextjs';

// For client components (hooks):
export function useApiClient() {
  const { getToken } = useAuth();

  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const token = await getToken();   // Clerk session token
    const res = await fetch(path, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new ApiError(res.status, err.detail ?? 'Request failed');
    }
    return res.json();
  }

  return {
    get: <T>(path: string) => request<T>('GET', path),
    post: <T>(path: string, body: unknown) => request<T>('POST', path, body),
  };
}

// For server components (SSR):
import { auth } from '@clerk/nextjs/server';

export async function serverApiRequest<T>(path: string): Promise<T> {
  const { getToken } = auth();
  const token = await getToken();
  const res = await fetch(`${process.env.INTERNAL_API_URL ?? 'http://localhost:8080'}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  });
  return res.json();
}
```

### Clerk Webhook — Sync User to Database

When a user signs up via Clerk, a webhook fires to create the corresponding row in the `users` table. This keeps the local DB in sync with Clerk's identity store.

```typescript
// app/api/webhooks/clerk/route.ts
import { Webhook } from 'svix';
import { headers } from 'next/headers';

export async function POST(req: Request) {
  const WEBHOOK_SECRET = process.env.CLERK_WEBHOOK_SECRET!;
  const headerPayload = headers();
  const svixId = headerPayload.get('svix-id');
  const svixTimestamp = headerPayload.get('svix-timestamp');
  const svixSignature = headerPayload.get('svix-signature');

  const body = await req.text();
  const wh = new Webhook(WEBHOOK_SECRET);

  let event: WebhookEvent;
  try {
    event = wh.verify(body, {
      'svix-id': svixId!,
      'svix-timestamp': svixTimestamp!,
      'svix-signature': svixSignature!,
    }) as WebhookEvent;
  } catch {
    return new Response('Invalid webhook signature', { status: 400 });
  }

  if (event.type === 'user.created') {
    // POST to Public API to insert into users table
    await fetch(`${process.env.INTERNAL_API_URL ?? 'http://localhost:8080'}/api/users/sync`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Webhook-Secret': process.env.INTERNAL_WEBHOOK_SECRET!,
      },
      body: JSON.stringify({
        clerk_user_id: event.data.id,
        email: event.data.email_addresses[0]?.email_address,
      }),
    });
  }

  return new Response('OK', { status: 200 });
}
```

---

## 4. Key Components

### 4.1 MapContainer.tsx

- Initialises Mapbox GL JS with style `mapbox://styles/mapbox/light-v11`
- Default centre: `-33.87, 151.21` (Sydney, centred for national scope), zoom `5`
- On `moveend`: debounce 400ms → fire `GET /api/search?bbox=...` via `usePropertySearch`
- Renders `PropertyMarker` per result; clusters at zoom < 13 (Mapbox built-in clustering)
- Renders `ZoneLayer` for active overlays (school zones, LGA boundaries)
- On parcel click: sets `selectedPropertyId` → `PropertyDetail` opens

### 4.2 SearchOmnibox.tsx

- Single input handles: address, suburb, postcode, LGA name, school name
- Debounce 300ms → `GET /api/search?q=...` with Cloudflare Turnstile token header
- Result types: `ADDRESS` → fly to property, `SUBURB/LGA` → fit bounds, `SCHOOL` → draw catchment polygon

### 4.3 PropertyDetail.tsx

- Slides in from right (CSS transition, 300ms)
- Fetches `GET /api/properties/{id}/detail` on open
- Shows loading skeleton during fetch
- Displays curated sections only: education, connectivity, risk factors, zoning/planning, demographic snapshot
- Exposes two download actions: anonymous/signed-in lite PDF and signed-in full PDF

### 4.4 DownloadButton.tsx

```typescript
// Flow:
// 1. User clicks button
// 2. If not signed in → Clerk's <SignInButton> modal opens
// 3. Signed-in users can download full PDF from GET /api/properties/{id}/full/pdf
// 4. Credit-based download enforcement is applied (1 credit per report, daily first, then purchased)
```

---

## 5. Disclaimer UI (Legal Requirement)

The following disclaimer must be visible in the footer of every page:

> **General Information Only.** OZ Property Report provides aggregated data for informational purposes only. It does not constitute financial, legal, or investment advice. Always seek independent professional advice before making investment decisions.

The Full Report must show a mandatory acknowledgement before revealing content:

```typescript
// FullReport.tsx
const [acknowledged, setAcknowledged] = useState(
  localStorage.getItem(`ack_${propertyId}`) === 'true'
);

if (!acknowledged) {
  return (
    <DisclaimerGate
      onAccept={() => {
        localStorage.setItem(`ack_${propertyId}`, 'true');
        setAcknowledged(true);
      }}
    />
  );
}
```

---

## 6. Performance Targets

| Metric | Target |
|---|---|
| Map pins load after bbox change | < 150ms API + < 50ms render |
| Lite panel data fetch | < 500ms |
| Omnibox suggestions | < 300ms after debounce |
| Initial page load (LCP) | < 2.5s |

---

## 7. Dockerfile

```dockerfile
FROM node:22-alpine AS base
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@latest --activate
COPY package.json pnpm-lock.yaml ./
RUN pnpm fetch --frozen-lockfile

FROM base AS builder
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM base AS runner
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
ENV NODE_ENV=production
CMD ["node", "server.js"]
```
