import type { Metadata } from 'next'
import { Newsreader, Hanken_Grotesk, DM_Mono } from 'next/font/google'
import { Analytics } from '@vercel/analytics/next'
import { ThemeProvider } from '@/components/theme-provider'
import './globals.css'

const newsreader = Newsreader({
  subsets: ['latin'],
  style: ['normal', 'italic'],
  variable: '--font-newsreader',
})

const hankenGrotesk = Hanken_Grotesk({
  subsets: ['latin'],
  variable: '--font-hanken',
})

const dmMono = DM_Mono({
  weight: ['300', '400', '500'],
  subsets: ['latin'],
  variable: '--font-dm-mono',
})

export const metadata: Metadata = {
  title: 'AXION — Scientific Intelligence System',
  description: 'Multi-agent AI research knowledge graph. Ingest papers, extract claims, detect contradictions, discover gaps, and synthesize research intelligence.',
  generator: 'AXION',
  icons: {
    icon: [
      {
        url: '/icon-light-32x32.png',
        media: '(prefers-color-scheme: light)',
      },
      {
        url: '/icon-dark-32x32.png',
        media: '(prefers-color-scheme: dark)',
      },
      {
        url: '/icon.svg',
        type: 'image/svg+xml',
      },
    ],
    apple: '/apple-icon.png',
  },
}

// Runs before first paint so the stored theme is applied without a flash.
const themeInitScript = `(function(){try{var t=localStorage.getItem('axion-theme');if(t!=='light'&&t!=='dark'&&t!=='system'){t='system'}var d=t==='dark'||(t==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);var r=document.documentElement;r.classList.toggle('dark',d);r.dataset.theme=t;r.style.colorScheme=d?'dark':'light'}catch(e){}})()`

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body
        className={`${newsreader.variable} ${hankenGrotesk.variable} ${dmMono.variable} cg-grid font-sans antialiased`}
        suppressHydrationWarning
      >
        <ThemeProvider>{children}</ThemeProvider>
        {/* The insights script is only served on Vercel deployments. Avoid
            requesting a missing /_vercel/insights route when self-hosting. */}
        {process.env.VERCEL === '1' && <Analytics />}
      </body>
    </html>
  )
}
