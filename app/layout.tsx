import './globals.css'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Finance Dashboard',
  description: 'Personal Finance Tracking Dashboard',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="th">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        {children}
      </body>
    </html>
  )
}

