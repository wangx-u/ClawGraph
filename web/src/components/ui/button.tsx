import Link from "next/link";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type ButtonProps = {
  children: ReactNode;
  href?: string;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  className?: string;
};

const styles = {
  primary:
    "bg-[linear-gradient(135deg,#3277ff,#16ccb3)] text-white shadow-glow hover:-translate-y-[1px] hover:brightness-105",
  secondary:
    "border bg-white/70 text-[color:var(--text)] hover:bg-white/90",
  ghost: "text-[color:var(--text-muted)] hover:bg-sky-500/5 hover:text-[color:var(--text)]",
  danger: "border border-rose-400/20 bg-rose-50 text-rose-700 hover:bg-rose-100"
};

export function Button({ children, href, variant = "secondary", className }: ButtonProps) {
  const classes = cn(
    "inline-flex items-center justify-center rounded-2xl px-4 py-2 text-sm font-medium transition duration-200",
    styles[variant],
    className
  );

  if (href) {
    return (
      <Link className={classes} href={href}>
        {children}
      </Link>
    );
  }

  return <button className={classes}>{children}</button>;
}
