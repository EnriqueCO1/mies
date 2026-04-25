"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import MiesLogo from "@/components/ui/MiesLogo";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      await api.login({ email, password });
      router.push("/chat");
    } catch (err: any) {
      setError(err.message || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-white flex flex-col items-center justify-center px-6">
      {/* Back to home */}
      <Link
        href="/"
        className="absolute top-8 left-8 text-[13px] text-[#86868b] hover:text-[#1c1c1e] transition-colors"
      >
        ← Volver
      </Link>

      <div className="w-full max-w-[400px]">
        {/* Logo */}
        <div className="flex justify-center mb-12">
          <div className="w-14 h-14 flex items-center justify-center">
            <MiesLogo size={32} />
          </div>
        </div>

        <h1 className="text-[32px] font-semibold text-[#1c1c1e] tracking-[-1px] text-center mb-2">
          Bienvenido
        </h1>
        <p className="text-[16px] text-[#48484a] text-center mb-10">
          Inicia sesión en tu cuenta de Mies
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 font-ui">
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="w-full bg-[#f5f5f7] text-[#1c1c1e] border border-black/[0.08] rounded-none px-5 py-4 text-[16px] placeholder:text-[#86868b] outline-none focus:border-black/20 transition-colors"
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="w-full bg-[#f5f5f7] text-[#1c1c1e] border border-black/[0.08] rounded-none px-5 py-4 text-[16px] placeholder:text-[#86868b] outline-none focus:border-black/20 transition-colors"
          />

          {error && (
            <p className="text-[13px] text-red-500 text-center">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-[#1c1c1e] text-white font-medium text-[16px] rounded-none py-4 mt-2 hover:scale-[1.02] hover:shadow-[0_4px_24px_rgba(0,0,0,0.08)] transition-all disabled:opacity-50 disabled:hover:scale-100"
          >
            {loading ? "Entrando..." : "Iniciar sesión"}
          </button>
        </form>

        <p className="text-[14px] text-[#86868b] text-center mt-8">
          ¿No tienes cuenta?{" "}
          <Link href="/register" className="text-[#1c1c1e] hover:text-black transition-colors">
            Registrarse
          </Link>
        </p>
      </div>
    </div>
  );
}
