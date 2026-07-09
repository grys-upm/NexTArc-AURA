export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen dot-grid flex items-center justify-center p-4">
      {children}
    </div>
  );
}
