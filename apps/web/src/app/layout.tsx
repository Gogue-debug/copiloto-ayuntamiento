import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Copiloto Administrativo — Ayuntamiento",
  description:
    "Asistente virtual para ciudadanos y herramientas de gestión para el personal del Ayuntamiento.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body className="antialiased bg-gray-50 text-gray-900">{children}</body>
    </html>
  );
}
