import "./globals.css";

export const metadata = {
  title: "Mars Mission — Arcadia Outpost",
  description: "Follow a persistent robotic outpost and inspect every decision.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
