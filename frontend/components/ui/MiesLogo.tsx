/**
 * Mies brand mark — the square-with-corner-dots geometry, static.
 *
 * Identical shape to the chat's rotating "Thinking" spinner (see
 * `app/chat/page.tsx`), minus the animation. Keeping the mark and the
 * loader geometrically aligned means the brand reads consistently:
 * the logo "comes alive" when Mies is thinking, settles back when idle.
 *
 * All measurements (2px bands, 6px corner dots, -1/-3 px offsets) are
 * deliberate — they produce an even 2-pixel split inside each dot so
 * the lines always read as cleanly bisecting each corner. Do not
 * parametrise these unless you're also rescaling the corner dots.
 *
 * The `size` prop is the big-square's side length. The actual visual
 * footprint is a touch larger because each corner dot protrudes 3 px
 * past each edge; allow ~6 px of breathing room in the parent.
 */

interface MiesLogoProps {
  /** Big-square side length in px. Default 24 (matches the chat loader). */
  size?: number;
  className?: string;
}

export default function MiesLogo({ size = 24, className = "" }: MiesLogoProps) {
  return (
    <div
      className={`relative ${className}`.trim()}
      style={{ width: `${size}px`, height: `${size}px` }}
      aria-hidden
    >
      {/* Four edge bands (2 px thick, extended 3 px past each corner so
          they run from the centre of one dot to the centre of the next). */}
      <div className="absolute -top-[1px] -left-[3px] -right-[3px] h-[2px] bg-[rgba(0,0,0,0.42)]" />
      <div className="absolute -bottom-[1px] -left-[3px] -right-[3px] h-[2px] bg-[rgba(0,0,0,0.42)]" />
      <div className="absolute -left-[1px] -top-[3px] -bottom-[3px] w-[2px] bg-[rgba(0,0,0,0.42)]" />
      <div className="absolute -right-[1px] -top-[3px] -bottom-[3px] w-[2px] bg-[rgba(0,0,0,0.42)]" />
      {/* Corner dots — 6×6, centred on each corner. Rendered on top of
          the edges so the edges appear to enter and exit each dot
          cleanly through its side-midpoints. */}
      <div className="absolute -top-[3px] -left-[3px] w-[6px] h-[6px] bg-white border border-[rgba(0,0,0,0.42)]" />
      <div className="absolute -top-[3px] -right-[3px] w-[6px] h-[6px] bg-white border border-[rgba(0,0,0,0.42)]" />
      <div className="absolute -bottom-[3px] -left-[3px] w-[6px] h-[6px] bg-white border border-[rgba(0,0,0,0.42)]" />
      <div className="absolute -bottom-[3px] -right-[3px] w-[6px] h-[6px] bg-white border border-[rgba(0,0,0,0.42)]" />
    </div>
  );
}
