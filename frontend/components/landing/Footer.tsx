export default function Footer() {
  return (
    <footer className="max-w-[1200px] mx-auto px-12 py-10 flex justify-between items-center border-t border-black/[0.06] max-md:flex-col max-md:gap-5 max-md:text-center">
      <div className="text-[13px] text-[#86868b]">
        © 2026 Mies. Todos los derechos reservados.
      </div>
      <div className="flex gap-7">
        <a href="#" className="text-[13px] text-[#86868b] hover:text-[#1c1c1e] transition-colors">
          Términos
        </a>
        <a href="#" className="text-[13px] text-[#86868b] hover:text-[#1c1c1e] transition-colors">
          Privacidad
        </a>
        <a href="#" className="text-[13px] text-[#86868b] hover:text-[#1c1c1e] transition-colors">
          Contacto
        </a>
      </div>
    </footer>
  );
}
