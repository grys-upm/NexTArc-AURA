"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { login } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

export default function LoginPage() {
  const router = useRouter();
  const [form, setForm] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    if (localStorage.getItem("aura_token")) {
      router.push("/dashboard");
    }
  }, [router]);

  // --- ADD THIS BLOCK TO SKIP LOGIN ---
  ///useEffect(() => {
  ///  if (mounted) {
  ///    // Set a dummy token (or a real one if you generated one via Postman)
  ///    localStorage.setItem("aura_token", "dev_bypass_token");
  ///    document.cookie = "aura_token=dev_bypass_token; path=/; max-age=604800; SameSite=Lax;";
  ///    router.push("/dashboard");
  ///  }
  ///}, [router, mounted]);
  // ------------------------------------

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const token = await login(form.username, form.password);
      localStorage.setItem("aura_token", token);
      document.cookie = `aura_token=${token}; path=/; max-age=604800; SameSite=Lax;`;
      router.push("/dashboard");
    } catch {
      setError("Invalid credentials");
    } finally {
      setLoading(false);
    }
  }

  // Prevent hydration mismatch errors
  if (!mounted) return null;

  return (
    <div className="w-full max-w-sm mx-auto animate-fade-in px-6">
      <div className="flex flex-col items-center gap-4 mb-8">

        {/* Logo aligned with the glowing style */}
        <div className="w-16 h-16 rounded-full bg-gradient-to-tr from-blue-200 to-emerald-100 dark:from-gray-700 dark:to-gray-800 p-1 shadow-xl">
          <div className="w-full h-full rounded-full bg-white dark:bg-gray-950 flex items-center justify-center border-2 border-white dark:border-gray-900 overflow-hidden relative">
            <Image
              src="/logo.png"
              alt="Aura Logo"
              fill // Makes the image occupy the entire container
              className="object-contain p-1" // p-1 to give it some breathing room inside the circle
              priority
            />
          </div>
        </div>

        <div className="text-center">
          <h1 className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-emerald-500">
            AURA Platform
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 font-mono">
            Edge AI Deployment
          </p>
        </div>
      </div>

      {/* Glassmorphism Login Card */}
      <div className="bg-white/40 dark:bg-gray-900/40 backdrop-blur-xl border border-gray-200 dark:border-gray-800 rounded-3xl p-8 shadow-sm">
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <Input
            label="Username"
            value={form.username}
            onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
            placeholder="admin"
            autoComplete="username"
            required
          />
          <Input
            label="Password"
            type="password"
            value={form.password}
            onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
            placeholder="••••••••"
            autoComplete="current-password"
            required
          />

          {error && (
            <div className="p-3 bg-red-50 dark:bg-red-900/10 border border-red-100 dark:border-red-900/20 rounded-lg text-center">
              <p className="text-xs font-medium text-red-600 dark:text-red-400">{error}</p>
            </div>
          )}

          <Button
            type="submit"
            loading={loading}
            className="w-full justify-center mt-2 px-4 py-2.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors shadow-sm"
          >
            {loading ? "Signing in..." : "Sign in"}
          </Button>
        </form>
      </div>
    </div>
  );
}