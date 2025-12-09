import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Voxly - Transcrição de Áudio",
  description: "Grave áudio, transcreva com Whisper e gere tópicos em Markdown",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}

