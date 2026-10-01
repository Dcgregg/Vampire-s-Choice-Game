import React from 'react';
import { GripVertical, Maximize2, Minimize2 } from 'lucide-react';

type Point = { x: number; y: number };

/** Desktop-only movable authoring window. Mobile deliberately remains a normal collapsible card. */
export const DesktopAdminPanel: React.FC<{ title: string; children: React.ReactNode; className?: string }> = ({ title, children, className = '' }) => {
  const [collapsed, setCollapsed] = React.useState(false);
  const [desktop, setDesktop] = React.useState(false);
  const [offset, setOffset] = React.useState<Point>({ x: 0, y: 0 });
  const dragStart = React.useRef<Point | null>(null);
  React.useEffect(() => { const media = window.matchMedia('(min-width: 1024px)'); const update = () => setDesktop(media.matches); update(); media.addEventListener('change', update); return () => media.removeEventListener('change', update); }, []);
  const move = (event: React.PointerEvent<HTMLButtonElement>) => { if (!desktop || !dragStart.current) return; setOffset({ x: event.clientX - dragStart.current.x, y: event.clientY - dragStart.current.y }); };
  const end = () => { dragStart.current = null; };
  return <section className={`rounded-xl border border-white/10 bg-[#150f1f] ${className}`} style={desktop ? { transform: `translate(${offset.x}px, ${offset.y}px)`, resize: 'both', overflow: 'auto', minWidth: 280 } : undefined}>
    <header className="flex items-center justify-between gap-2 border-b border-white/10 px-3 py-2"><div className="flex items-center gap-2"><button type="button" aria-label={`Move ${title} window`} onPointerDown={(event) => { if (!desktop) return; dragStart.current = { x: event.clientX - offset.x, y: event.clientY - offset.y }; event.currentTarget.setPointerCapture(event.pointerId); }} onPointerMove={move} onPointerUp={end} onPointerCancel={end} className="hidden cursor-grab text-stone-500 active:cursor-grabbing lg:block"><GripVertical className="h-4 w-4" /></button><h2 className="text-sm font-semibold uppercase tracking-wider text-[#c5a059]">{title}</h2></div><button type="button" onClick={() => setCollapsed((value) => !value)} className="rounded p-1 text-stone-300" aria-expanded={!collapsed} aria-label={`${collapsed ? 'Expand' : 'Collapse'} ${title}`}>{collapsed ? <Maximize2 className="h-4 w-4" /> : <Minimize2 className="h-4 w-4" />}</button></header>
    {!collapsed && <div className="p-4">{children}</div>}
  </section>;
};
