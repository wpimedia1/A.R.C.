import "./globals.css";

export const metadata = {
  title: "A.R.C. — Autonomous Robotic Colony",
  description: "Follow a persistent robotic outpost and inspect every decision.",
  icons: {icon: "/icon.svg"},
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

import './journey.css';
