"use client";

import Link from "next/link";
import MiesLogo from "@/components/ui/MiesLogo";

export default function Navbar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-12 py-5 bg-white/80 backdrop-blur-xl border-b border-black/[0.06]">
      {/* Logo */}
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 flex items-center justify-center shrink-0">
          <MiesLogo size={20} />
        </div>
        {/* Major Mono Display — strict 90° geometry, architecture-brand
            feel. Single weight (400); lowercase letters render as smaller
            uppercase forms. `tracking` slightly tightened so "MIES"
            reads as a single glyph block rather than four isolated
            letters. */}
        <span className="font-['Major_Mono_Display'] text-[17px] text-[#1c1c1e] tracking-[-0.5px] leading-none">
          Mies
        </span>
      </div>

      {/* Links */}
      <ul className="hidden md:flex gap-9">
        <li>
          <a href="#features" className="text-[#86868b] text-sm hover:text-[#1c1c1e] transition-colors">
            Funcionalidades
          </a>
        </li>
        <li>
          <a href="#how" className="text-[#86868b] text-sm hover:text-[#1c1c1e] transition-colors">
            Cómo funciona
          </a>
        </li>
        <li>
          <a href="#pricing" className="text-[#86868b] text-sm hover:text-[#1c1c1e] transition-colors">
            Precios
          </a>
        </li>
      </ul>

      {/* Auth buttons */}
      <div className="flex items-center gap-3 font-ui">
        <Link
          href="/login"
          className="text-[13px] font-medium text-[#48484a] border border-black/[0.15] rounded-none px-6 py-2.5 hover:text-[#1c1c1e] hover:border-black/30 transition-all"
        >
          Entrar
        </Link>
        <Link
          href="/register"
          className="text-[13px] font-medium text-white bg-[#1c1c1e] rounded-none px-6 py-2.5 hover:scale-[1.04] hover:shadow-[0_4px_20px_rgba(0,0,0,0.1)] transition-all"
        >
          Registro
        </Link>
      </div>
    </nav>
  );
}
