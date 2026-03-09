"use client";

import { useEffect, useMemo, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import NavBar from "@/components/navbar";
import Scanner from "@/components/scanner";
import { supabase } from "@/lib/supabaseClient";

function toInternalEmail(username: string): string {
  const normalized = username.trim().toLowerCase().replace(/[^a-z0-9._-]/g, "");
  return `${normalized}@pokehunter.local`;
}

export default function ScannerPage() {
  const [session, setSession] = useState<Session | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"sign-in" | "sign-up">("sign-in");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const envReady = useMemo(
    () =>
      Boolean(
        process.env.NEXT_PUBLIC_SUPABASE_URL &&
          process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
      ),
    [],
  );

  useEffect(() => {
    if (!envReady || !supabase) {
      setLoading(false);
      setError(
        "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY in frontend env.",
      );
      return;
    }

    supabase.auth
      .getSession()
      .then(({ data }) => setSession(data.session))
      .finally(() => setLoading(false));

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, currentSession) => {
      setSession(currentSession);
    });

    return () => subscription.unsubscribe();
  }, [envReady]);

  async function handleAuthSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);

    const normalizedUsername = username.trim().toLowerCase();
    if (!normalizedUsername) {
      setError("Username is required.");
      return;
    }
    if (password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }

    const email = toInternalEmail(normalizedUsername);
    if (!supabase) {
      setError(
        "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY in frontend env.",
      );
      return;
    }
    setSubmitting(true);
    try {
      if (mode === "sign-up") {
        const { error: signUpError } = await supabase.auth.signUp({
          email,
          password,
          options: { data: { username: normalizedUsername } },
        });
        if (signUpError) throw signUpError;
      } else {
        const { error: signInError } = await supabase.auth.signInWithPassword({
          email,
          password,
        });
        if (signInError) throw signInError;
      }
    } catch (authError) {
      setError(authError instanceof Error ? authError.message : "Auth failed.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLogout() {
    if (!supabase) return;
    await supabase.auth.signOut();
  }

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-gradient-to-br from-purple-100 via-blue-50 to-purple-50 text-black">
        Loading...
      </div>
    );
  }

  if (!session) {
    return (
      <div className="h-screen bg-gradient-to-br from-purple-100 via-blue-50 to-purple-50 flex items-center justify-center px-4">
        <div className="w-full max-w-md bg-white rounded-2xl shadow-lg border border-gray-200 p-6 text-black">
          <h1 className="text-2xl font-bold mb-1">PokéHunter Auth</h1>
          <p className="text-sm text-gray-600 mb-5">
            Super simple login with username + password.
          </p>

          <form className="space-y-3" onSubmit={handleAuthSubmit}>
            <input
              type="text"
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2"
              required
            />
            <input
              type="password"
              placeholder="Password (min 6)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2"
              required
              minLength={6}
            />

            <button
              type="submit"
              disabled={submitting || !envReady}
              className="w-full bg-gray-900 text-white rounded-lg py-2 font-medium disabled:opacity-60"
            >
              {submitting
                ? "Please wait..."
                : mode === "sign-in"
                  ? "Sign In"
                  : "Sign Up"}
            </button>
          </form>

          <button
            type="button"
            onClick={() =>
              setMode((m) => (m === "sign-in" ? "sign-up" : "sign-in"))
            }
            className="mt-3 text-sm text-purple-700 underline"
          >
            {mode === "sign-in"
              ? "Need an account? Sign up"
              : "Already have an account? Sign in"}
          </button>

          {error && <div className="mt-3 text-sm text-red-600">{error}</div>}
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen bg-gradient-to-br from-purple-100 via-blue-50 to-purple-50 flex flex-col overflow-hidden">
      <NavBar currentPage={"scan"} />
      <div className="max-w-7xl mx-auto w-[80%] px-8 pt-4">
        <button
          type="button"
          onClick={handleLogout}
          className="text-sm text-gray-800 bg-white border rounded-md px-3 py-1"
        >
          Log out
        </button>
      </div>
      <div className="flex-1 my-4 overflow-auto max-w-7xl mx-auto w-[80%] px-8 py-6">
        <Scanner userId={session.user.id} />
      </div>
    </div>
  );
}
