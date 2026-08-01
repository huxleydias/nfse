import { useEffect, useState } from "react"
import { Outlet, useNavigate } from "react-router-dom"
import { AppSidebar } from "@/components/app-sidebar"
import { SiteHeader } from "@/components/site-header"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { api } from "@/lib/api"

export default function Layout() {
  const navigate = useNavigate()
  const [empresa, setEmpresa] = useState("")

  useEffect(() => {
    api
      .obterConfig()
      .then((config) => setEmpresa(config.prestador.razao_social ?? ""))
      .catch(() => setEmpresa(""))
  }, [])

  async function sair() {
    await api.logout()
    navigate("/login")
  }

  return (
    <SidebarProvider
      style={
        {
          "--sidebar-width": "16rem",
          "--header-height": "3.5rem",
        } as React.CSSProperties
      }
    >
      <AppSidebar empresa={empresa} onSair={sair} />
      <SidebarInset>
        <SiteHeader />
        <main className="flex flex-1 flex-col p-4 lg:p-6">
          <div className="mx-auto w-full max-w-7xl">
            <Outlet />
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}
