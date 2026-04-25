import Navbar from "@/components/landing/Navbar";
import Hero from "@/components/landing/Hero";
import Features from "@/components/landing/Features";
import HowItWorks from "@/components/landing/HowItWorks";
import Pricing from "@/components/landing/Pricing";
import Footer from "@/components/landing/Footer";

export default function Home() {
  return (
    <main className="bg-white text-[#1c1c1e] min-h-screen overflow-x-hidden">
      <Navbar />
      <Hero />
      <div className="max-w-[1200px] mx-auto h-px bg-black/[0.06]" />
      <Features />
      <div className="max-w-[1200px] mx-auto h-px bg-black/[0.06]" />
      <HowItWorks />
      <div className="max-w-[1200px] mx-auto h-px bg-black/[0.06]" />
      <Pricing />
      <Footer />
    </main>
  );
}
