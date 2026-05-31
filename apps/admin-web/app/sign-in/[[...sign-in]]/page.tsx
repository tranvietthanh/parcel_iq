import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold text-gray-900">OZ Property Report Admin</h1>
          <p className="mt-2 text-sm text-gray-600">
            Sign in to access the admin console
          </p>
        </div>
        <SignIn />
      </div>
    </div>
  );
}
