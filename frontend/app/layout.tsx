import type { Metadata } from "next";
import { ThemeProvider } from "@/components/ThemeProvider";
import "./globals.css";

export const metadata: Metadata = {
  title: "AURA Platform",
  description: "Edge AI Deployment Platform",
  // Add this icons property:
  icons: {
    icon: "/logo.png", // Points directly to public/logo.png
    apple: "/logo.png", // Optional: Also uses it for iOS home screen bookmarks
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="scroll-smooth" suppressHydrationWarning>
      <body className="bg-slate-200/40 dark:bg-gray-950 text-gray-900 dark:text-gray-100 transition-colors duration-300 antialiased selection:bg-blue-200 selection:text-blue-900">
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
        >
          {/* We removed the old <header> with the ThemeToggle that was here */}
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}