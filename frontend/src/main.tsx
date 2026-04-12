import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { ThemeProvider } from "next-themes"

import App from "./App.tsx"
import { Toaster } from "@/components/ui/sonner"
import "./index.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
      <App />
      <Toaster richColors closeButton position="bottom-center" />
    </ThemeProvider>
  </StrictMode>,
)
