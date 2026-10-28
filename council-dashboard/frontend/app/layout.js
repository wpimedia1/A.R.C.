import "./globals.css";

export const metadata = {
  title: "Mars Council",
  description: "Multi-agent council dashboard: Mars colony crisis deliberation",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
