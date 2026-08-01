import { Link } from "react-router-dom"
import {
  FileBadgeIcon,
  FilePlus2Icon,
  FileTextIcon,
  LogOutIcon,
  Settings2Icon,
  ShieldCheckIcon,
} from "lucide-react"
import { NavMain } from "@/components/nav-main"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"

const itens = [
  { title: "Notas fiscais", url: "/notas", icon: FileTextIcon },
  { title: "Emitir nota", url: "/emitir", icon: FilePlus2Icon },
  { title: "Configuracao", url: "/config", icon: Settings2Icon },
  { title: "Certificado", url: "/certificado", icon: ShieldCheckIcon },
]

export function AppSidebar({
  empresa,
  onSair,
  ...props
}: React.ComponentProps<typeof Sidebar> & {
  empresa: string
  onSair: () => void
}) {
  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild size="lg">
              <Link to="/notas">
                <span className="flex aspect-square size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                  <FileBadgeIcon className="size-4" />
                </span>
                <span className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-semibold">NFS-e Sao Paulo</span>
                  <span className="truncate text-xs text-muted-foreground">
                    {empresa || "Emissor de notas"}
                  </span>
                </span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={itens} />
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton onClick={onSair} tooltip="Sair">
              <LogOutIcon />
              <span>Sair</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}
