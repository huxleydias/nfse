import { Link, useLocation } from "react-router-dom"
import { PlusIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"

const titulos: Record<string, string> = {
  "/notas": "Notas fiscais",
  "/emitir": "Emitir nota",
  "/config": "Configuracao",
  "/certificado": "Certificado digital",
}

export function SiteHeader() {
  const { pathname } = useLocation()

  return (
    <header className="flex h-(--header-height) shrink-0 items-center gap-2 border-b bg-background transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-(--header-height)">
      <div className="flex w-full items-center gap-1 px-4 lg:gap-2 lg:px-6">
        <SidebarTrigger className="-ml-1" />
        <Separator orientation="vertical" className="mx-2 data-[orientation=vertical]:h-4" />
        <h1 className="text-base font-medium">{titulos[pathname] ?? "NFS-e"}</h1>
        {pathname !== "/emitir" && (
          <Button asChild size="sm" className="ml-auto">
            <Link to="/emitir">
              <PlusIcon />
              Nova nota
            </Link>
          </Button>
        )}
      </div>
    </header>
  )
}
