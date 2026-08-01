import { useEffect, useState } from "react"
import { NavLink, Outlet, useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"

const links = [
  { to: "/notas", label: "Notas" },
  { to: "/emitir", label: "Emitir" },
  { to: "/config", label: "Configuracao" },
  { to: "/certificado", label: "Certificado" },
]

export default function Layout() {
  const navigate = useNavigate()
  // A marca no cabecalho vem da razao social configurada, nao do codigo:
  // cada instalacao mostra a propria empresa.
  const [empresa, setEmpresa] = useState("")

  useEffect(() => {
    api
      .obterConfig()
      .then((c) => setEmpresa(c.prestador.razao_social ?? ""))
      .catch(() => setEmpresa(""))
  }, [])

  async function sair() {
    await api.logout()
    navigate("/login")
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-8">
            <span className="text-lg font-bold">
              <span className="text-primary">NFS-e</span>
              {empresa && (
                <span
                  className="ml-2 text-sm font-normal text-muted-foreground"
                  title={empresa}
                >
                  {empresa.length > 32 ? `${empresa.slice(0, 32)}...` : empresa}
                </span>
              )}
            </span>
            <nav className="flex gap-1">
              {links.map((l) => (
                <NavLink
                  key={l.to}
                  to={l.to}
                  className={({ isActive }) =>
                    cn(
                      "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:text-foreground",
                    )
                  }
                >
                  {l.label}
                </NavLink>
              ))}
            </nav>
          </div>
          <Button variant="ghost" size="sm" onClick={sair}>
            Sair
          </Button>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
