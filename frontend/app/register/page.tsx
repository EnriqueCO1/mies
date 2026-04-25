"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [colegiado, setColegiado] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleRegister = async () => {
    setError("");
    setLoading(true);
    try {
      await api.register({
        email,
        password,
        name,
        colegiado_number: colegiado || undefined,
      });
      router.push("/chat");
    } catch (err: any) {
      setError(err.message || "Error en el registro");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-white flex flex-col items-center justify-center px-6">
      <Link
        href="/"
        className="absolute top-8 left-8 text-[13px] text-[#86868b] hover:text-[#1c1c1e] transition-colors"
      >
        ← Volver
      </Link>

      <div className="w-full max-w-[440px] font-ui">
        {/* Step indicator */}
        <div className="font-mono text-[11px] text-[#86868b] tracking-[2px] uppercase text-center mb-10">
          Paso {step} de 2
        </div>

        {/* Step 1: Credentials */}
        {step === 1 && (
          <div className="flex flex-col items-center">
            <h1 className="text-[36px] font-semibold text-[#1c1c1e] tracking-[-1.5px] text-center mb-3">
              Crear cuenta
            </h1>
            <p className="text-[16px] text-[#48484a] text-center mb-10">
              Empieza a trabajar con Mies.
            </p>

            <div className="w-full flex flex-col gap-4">
              <input
                type="text"
                placeholder="Nombre"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full bg-[#f5f5f7] text-[#1c1c1e] border border-black/[0.08] rounded-none px-5 py-4 text-[16px] placeholder:text-[#86868b] outline-none focus:border-black/20 transition-colors"
              />
              <input
                type="email"
                placeholder="Email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-[#f5f5f7] text-[#1c1c1e] border border-black/[0.08] rounded-none px-5 py-4 text-[16px] placeholder:text-[#86868b] outline-none focus:border-black/20 transition-colors"
              />
              <input
                type="password"
                placeholder="Contraseña"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-[#f5f5f7] text-[#1c1c1e] border border-black/[0.08] rounded-none px-5 py-4 text-[16px] placeholder:text-[#86868b] outline-none focus:border-black/20 transition-colors"
              />

              <button
                onClick={() => {
                  if (name && email && password) setStep(2);
                }}
                disabled={!name || !email || !password}
                className="w-full bg-[#1c1c1e] text-white font-medium text-[16px] rounded-none py-4 mt-4 hover:scale-[1.02] transition-all disabled:opacity-30 disabled:hover:scale-100"
              >
                Continuar
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Optional colegiado + confirm */}
        {step === 2 && (
          <div className="flex flex-col items-center">
            <h1 className="text-[36px] font-semibold text-[#1c1c1e] tracking-[-1.5px] text-center mb-3">
              Casi listo, {name}
            </h1>
            <p className="text-[16px] text-[#48484a] text-center mb-10">
              Si tienes número de colegiado, indícalo.
            </p>

            <div className="w-full flex flex-col gap-4">
              <input
                type="text"
                placeholder="Número de colegiado (opcional)"
                value={colegiado}
                onChange={(e) => setColegiado(e.target.value)}
                className="w-full bg-[#f5f5f7] text-[#1c1c1e] border border-black/[0.08] rounded-none px-5 py-4 text-[16px] placeholder:text-[#86868b] outline-none focus:border-black/20 transition-colors"
              />

              {error && (
                <p className="text-[13px] text-red-500 text-center">{error}</p>
              )}

              <button
                onClick={handleRegister}
                disabled={loading}
                className="w-full bg-[#1c1c1e] text-white font-medium text-[16px] rounded-none py-4 mt-2 hover:scale-[1.02] hover:shadow-[0_4px_24px_rgba(0,0,0,0.08)] transition-all disabled:opacity-50 disabled:hover:scale-100"
              >
                {loading ? "Creando cuenta..." : "Crear cuenta"}
              </button>
            </div>

            <button
              onClick={() => setStep(1)}
              className="block mx-auto mt-6 text-[14px] text-[#86868b] hover:text-[#1c1c1e] transition-colors"
            >
              ← Volver
            </button>
          </div>
        )}

        {step === 1 && (
          <p className="text-[14px] text-[#86868b] text-center mt-8">
            ¿Ya tienes cuenta?{" "}
            <Link href="/login" className="text-[#1c1c1e] hover:text-black transition-colors">
              Iniciar sesión
            </Link>
          </p>
        )}
      </div>
    </div>
  );
}
