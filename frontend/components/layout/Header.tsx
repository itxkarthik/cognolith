"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/hooks/useAuth";
import { Search, Bell, Settings, User, LogOut } from "lucide-react";

export function Header() {
  const router = useRouter();
  const { logout } = useAuth();
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  return (
    <header className="fixed top-0 right-0 left-64 z-30 flex justify-between items-center px-8 h-16 bg-[#131313]/60 backdrop-blur-xl border-b border-[#464554]/20 font-['Inter'] font-medium tracking-tight">
      <div className="flex items-center gap-8">
        <div className="relative flex items-center">
          <Search className="absolute left-3 text-[#908fa0] w-4 h-4" />
          <input
            className="bg-[#0e0e0e] border-none rounded-xl pl-10 pr-4 py-2 text-xs w-64 focus:ring-1 focus:ring-[#bcff5f]/50 text-[#e2e2e2] placeholder-[#908fa0]/60"
            placeholder="Search knowledge graph..."
            type="text"
          />
        </div>
        <nav className="flex gap-6 text-sm">
          <a className="text-[#e2e2e2]/70 hover:text-[#bcff5f] transition-colors cursor-pointer">
            Systems
          </a>
          <a className="text-[#e2e2e2]/70 hover:text-[#bcff5f] transition-colors cursor-pointer">
            Logs
          </a>
          <a className="text-[#e2e2e2]/70 hover:text-[#bcff5f] transition-colors cursor-pointer">
            Terminal
          </a>
        </nav>
      </div>
      <div className="flex items-center gap-4">
        <button
          className="text-[#e2e2e2]/70 hover:text-[#bcff5f] transition-colors"
          aria-label="Notifications"
        >
          <Bell className="w-5 h-5" />
        </button>
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              className="text-[#e2e2e2]/70 hover:text-[#bcff5f] transition-colors"
              aria-label="Settings"
            >
              <Settings className="w-5 h-5" />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              sideOffset={10}
              className="z-50 min-w-48 rounded-xl border border-[#464554]/30 bg-[#1f1f1f] p-2 text-[#e2e2e2] shadow-2xl"
            >
              <DropdownMenu.Item
                onClick={() => router.push("/dashboard/settings")}
                className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm outline-none transition hover:bg-[#2a2a2a] text-[#e2e2e2]/80"
              >
                <User className="w-4 h-4" />
                Profile
              </DropdownMenu.Item>
              <DropdownMenu.Separator className="my-1 h-px bg-[#464554]/20" />
              <DropdownMenu.Item
                onClick={async () => {
                  if (isLoggingOut) return;
                  setIsLoggingOut(true);
                  try {
                    await logout();
                    router.replace("/auth/login");
                  } finally {
                    setIsLoggingOut(false);
                  }
                }}
                className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm text-[#ffb4ab] outline-none transition hover:bg-[#ffb4ab]/10"
              >
                <LogOut className="w-4 h-4" />
                {isLoggingOut ? "Logging out..." : "Logout"}
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>
    </header>
  );
}
