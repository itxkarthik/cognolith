"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/hooks/useAuth";
import {
  LayoutDashboard,
  Database,
  FileText,
  MessageSquare,
  BarChart3,
  Settings,
  HelpCircle,
  Terminal,
  Plus,
} from "lucide-react";

const iconMap: Record<string, React.ReactNode> = {
  dashboard: <LayoutDashboard className="w-4 h-4" />,
  database: <Database className="w-4 h-4" />,
  description: <FileText className="w-4 h-4" />,
  smart_toy: <MessageSquare className="w-4 h-4" />,
  monitoring: <BarChart3 className="w-4 h-4" />,
  settings: <Settings className="w-4 h-4" />,
  help: <HelpCircle className="w-4 h-4" />,
};

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: "dashboard" },
  {
    href: "/dashboard/knowledge-graph",
    label: "Knowledge Base",
    icon: "database",
  },
  { href: "/dashboard/documents", label: "Documents", icon: "description" },
  { href: "/dashboard/notes", label: "Notes", icon: "description" },
  { href: "/dashboard/chat", label: "Chat Assistant", icon: "smart_toy" },
  { href: "/dashboard/search", label: "Analytics", icon: "monitoring" },
];

const secondaryNavItems = [
  { href: "/dashboard/settings", label: "Settings", icon: "settings" },
  { href: "#support", label: "Support", icon: "help" },
];

interface NavItemProps {
  item: { href: string; label: string; icon: string };
  isActive: boolean;
}

function NavItem({ item, isActive }: NavItemProps) {
  return (
    <Link
      href={item.href}
      className={`px-4 py-3 flex items-center gap-3 transition-all duration-300 text-sm tracking-tight ${
        isActive
          ? "text-[#c0c1ff] bg-[#1b1b1b] border-l-2 border-[#bcff5f]"
          : "text-[#e2e2e2]/60 hover:text-[#e2e2e2] hover:bg-[#1b1b1b] hover:text-[#bcff5f]"
      }`}
    >
      <div className="flex-shrink-0">
        {iconMap[item.icon] || iconMap.dashboard}
      </div>
      <span className="text-xs font-medium">{item.label}</span>
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const { user } = useAuth();

  return (
    <aside className="fixed left-0 top-0 h-full z-40 flex flex-col bg-[#131313] w-64 border-r border-[#464554]/20 font-['Inter'] text-sm tracking-tight hidden lg:flex">
      <div className="p-6">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-8 h-8 rounded bg-[#8083ff] flex items-center justify-center">
            <Terminal className="w-4 h-4 text-[#07006c]" />
          </div>
          <div>
            <h1 className="text-lg font-black tracking-tighter text-[#e2e2e2]">
              Personal AI Knowledge Assistant
            </h1>
            <p className="text-[10px] uppercase font-bold font-['Space_Grotesk'] text-[#c0c1ff]/60 tracking-widest">
              High-Performance Assistant
            </p>
          </div>
        </div>

        <button className="w-full font-bold py-3 px-4 rounded-xl flex items-center justify-center gap-2 mb-8 hover:opacity-90 transition-all bg-[#1a1a1a] border border-[#464554]/30 text-[#e2e2e2] hover:bg-[#252525]">
          <Plus className="w-4 h-4" />
          <span className="text-xs font-bold">New Entry</span>
        </button>

        <nav className="space-y-1">
          {navItems.map((item) => {
            const isActive =
              pathname === item.href ||
              (item.href !== "/dashboard" && pathname.startsWith(item.href));
            return <NavItem key={item.href} item={item} isActive={isActive} />;
          })}
        </nav>
      </div>

      <div className="mt-auto p-6 space-y-1">
        <nav className="space-y-1">
          {secondaryNavItems.map((item) => {
            const isActive = pathname === item.href;
            return <NavItem key={item.href} item={item} isActive={isActive} />;
          })}
        </nav>

        <div className="pt-6 flex items-center gap-3 border-t border-[#464554]/10">
          <div className="w-8 h-8 rounded-full bg-[#353535] overflow-hidden flex items-center justify-center text-[#e2e2e2]/60 font-bold text-xs">
            {user?.full_name?.[0]?.toUpperCase() ?? "U"}
          </div>
          <div className="overflow-hidden">
            <p className="text-xs font-bold text-[#e2e2e2] truncate">
              {user?.full_name ?? "Operator_01"}
            </p>
            <p className="text-[10px] text-[#908fa0] truncate uppercase font-['Space_Grotesk'] text-[11px]">
              Status: Active
            </p>
          </div>
        </div>
      </div>
    </aside>
  );
}
