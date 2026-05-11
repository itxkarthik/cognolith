"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/hooks/useAuth";
import { motion } from "motion/react";
import { Search, Bell, Settings, User, LogOut } from "lucide-react";
import {
  Badge,
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Input,
  Separator,
} from "@/components/ui";

export function Header() {
  const router = useRouter();
  const { logout } = useAuth();
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  return (
    <header className="fixed left-72 right-0 top-0 z-30 border-b border-cyan-500/25 bg-[#060916]/80 backdrop-blur-xl" style={{ boxShadow: "0 0 20px rgba(0, 255, 255, 0.1)" }}>
      <div className="flex h-16 items-center justify-between px-8 relative">
        {/* Animated border line */}
        <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-cyan-500/0 via-cyan-500/50 to-cyan-500/0" />

        <div className="flex items-center gap-6">
          <div className="relative w-[24rem] max-w-[42vw] group">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-cyan-400/50 group-focus-within:text-cyan-400 transition-colors" />
            <Input
              className="h-11 rounded-full border-cyan-500/35 bg-cyan-500/10 pl-10 text-sm text-cyan-50 placeholder:text-cyan-400/45 focus-visible:border-cyan-400/70 focus-visible:ring-cyan-500/50"
              placeholder="Search knowledge graph..."
              type="text"
            />
          </div>
          <div className="hidden items-center gap-2 xl:flex">
            <Badge variant="secondary" className="rounded-full bg-cyan-500/10 border border-cyan-500/30 px-3 py-1 text-cyan-400 hover:bg-cyan-500/20 cursor-pointer transition-colors">
              Systems
            </Badge>
            <Badge variant="outline" className="rounded-full border-cyan-500/20 bg-cyan-500/5 px-3 py-1 text-cyan-300/70 hover:border-cyan-500/40 hover:bg-cyan-500/10 cursor-pointer transition-all">
              Logs
            </Badge>
            <Badge variant="outline" className="rounded-full border-teal-500/25 bg-teal-500/8 px-3 py-1 text-teal-200/70 hover:border-teal-400/45 hover:bg-teal-500/15 cursor-pointer transition-all">
              Terminal
            </Badge>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <motion.div whileHover={{ y: -2 }} whileTap={{ scale: 0.97 }} transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}>
            <Button variant="ghost" size="icon" className="rounded-full text-cyan-400/70 hover:bg-cyan-500/10 hover:text-cyan-300 transition-all" style={{ textShadow: "0 0 8px rgba(0, 255, 255, 0.3)" }}>
            <Bell className="h-5 w-5" />
            <span className="sr-only">Notifications</span>
          </Button>
          </motion.div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="rounded-full text-cyan-400/70 hover:bg-cyan-500/10 hover:text-cyan-300 transition-all" style={{ textShadow: "0 0 8px rgba(0, 255, 255, 0.3)" }}>
                <Settings className="h-5 w-5" />
                <span className="sr-only">Settings</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56 rounded-xl border border-cyan-500/20 bg-[#1a1f3a]/80 p-2 text-cyan-50 shadow-2xl backdrop-blur-lg" style={{ boxShadow: '0 0 20px rgba(0, 255, 255, 0.15)' }}>
              <DropdownMenuItem
                onClick={() => router.push("/dashboard/settings")}
                className="cursor-pointer rounded-lg px-3 py-2 text-sm text-cyan-300/85 hover:bg-cyan-500/10 transition-all"
              >
                <User className="mr-2 h-4 w-4" />
                Profile
              </DropdownMenuItem>
              <DropdownMenuSeparator className="my-1 bg-cyan-500/10" />
              <DropdownMenuItem
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
                className="cursor-pointer rounded-lg px-3 py-2 text-sm text-pink-400/90 hover:bg-pink-500/10 transition-all"
              >
                <LogOut className="mr-2 h-4 w-4" />
                {isLoggingOut ? "Logging out..." : "Logout"}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
      <Separator className="bg-white/10" />
    </header>
  );
}
