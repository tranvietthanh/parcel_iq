import { Webhook } from "svix";
import { headers } from "next/headers";

type WebhookEvent = {
  type: string;
  data: {
    id: string;
    deleted?: boolean;
    email_addresses: Array<{ email_address: string }>;
  };
};

export async function POST(req: Request) {
  const WEBHOOK_SECRET = process.env.CLERK_WEBHOOK_SECRET;
  if (!WEBHOOK_SECRET) {
    return new Response("Missing CLERK_WEBHOOK_SECRET", { status: 500 });
  }

  const headerPayload = await headers();
  const svixId = headerPayload.get("svix-id");
  const svixTimestamp = headerPayload.get("svix-timestamp");
  const svixSignature = headerPayload.get("svix-signature");

  if (!svixId || !svixTimestamp || !svixSignature) {
    return new Response("Missing svix headers", { status: 400 });
  }

  const body = await req.text();
  const wh = new Webhook(WEBHOOK_SECRET);

  let event: WebhookEvent;
  try {
    event = wh.verify(body, {
      "svix-id": svixId,
      "svix-timestamp": svixTimestamp,
      "svix-signature": svixSignature,
    }) as WebhookEvent;
  } catch {
    return new Response("Invalid webhook signature", { status: 400 });
  }

  const internalHeaders = {
    "Content-Type": "application/json",
    "X-Webhook-Secret": process.env.INTERNAL_WEBHOOK_SECRET!,
  };
  const apiUrl = process.env.INTERNAL_API_URL ?? "http://localhost:8080";


  if (event.type === "user.created" || event.type === "user.updated") {
    const email = event.data.email_addresses?.[0]?.email_address;
    if (email) {
      await fetch(`${apiUrl}/api/users/sync`, {
        method: "POST",
        headers: internalHeaders,
        body: JSON.stringify({ clerk_user_id: event.data.id, email }),
      });
    }
  } else if (event.type === "user.deleted") {
    await fetch(`${apiUrl}/api/users/sync/${event.data.id}`, {
      method: "DELETE",
      headers: internalHeaders,
    });
  }

  return new Response("OK", { status: 200 });
}
