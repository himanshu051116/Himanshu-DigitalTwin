import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'HimanshuDigitalTwin',
  description: 'Adaptive metabolic digital twin research prototype for Type-2 diabetes',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
