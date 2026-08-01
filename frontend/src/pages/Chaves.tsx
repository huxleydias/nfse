import { useEffect, useState } from "react"
import { toast } from "sonner"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { api, ApiError, type ChaveApi } from "@/lib/api"

function formatarData(iso: string | null) {
  if (!iso) return "nunca"
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })
}

export default function Chaves() {
  const [chaves, setChaves] = useState<ChaveApi[]>([])
  const [nome, setNome] = useState("")
  const [criando, setCriando] = useState(false)
  const [novaChave, setNovaChave] = useState<string | null>(null)
  const [revogando, setRevogando] = useState<ChaveApi | null>(null)
  const urlMcp = `${window.location.origin}/mcp`

  async function carregar() {
    try {
      const r = await api.listarChaves()
      setChaves(r.chaves)
    } catch {
      toast.error("Falha ao carregar as chaves")
    }
  }

  useEffect(() => {
    carregar()
  }, [])

  async function criar(evento: React.FormEvent) {
    evento.preventDefault()
    if (!nome.trim()) {
      toast.error("De um nome para a chave")
      return
    }
    setCriando(true)
    try {
      const r = await api.criarChave(nome.trim())
      setNovaChave(r.valor)
      setNome("")
      carregar()
    } catch (erro) {
      toast.error(erro instanceof ApiError ? erro.message : "Falha ao criar a chave")
    } finally {
      setCriando(false)
    }
  }

  async function confirmarRevogacao() {
    if (!revogando) return
    try {
      await api.revogarChave(revogando.id)
      toast.success(`Chave ${revogando.nome} revogada`)
      setRevogando(null)
      carregar()
    } catch {
      toast.error("Falha ao revogar")
    }
  }

  async function copiar(texto: string, rotulo: string) {
    try {
      await navigator.clipboard.writeText(texto)
      toast.success(`${rotulo} copiado`)
    } catch {
      toast.error("Nao foi possivel copiar. Selecione e copie manualmente.")
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Chaves de API</h2>
        <p className="text-sm text-muted-foreground">
          Uma chave autentica tanto a API REST quanto o servidor MCP.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Criar chave</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={criar} className="flex flex-wrap items-end gap-3">
            <div className="min-w-56 flex-1 space-y-2">
              <Label htmlFor="nome">Nome</Label>
              <Input
                id="nome"
                value={nome}
                placeholder="n8n, Claude Desktop, integracao da loja"
                maxLength={80}
                onChange={(e) => setNome(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Serve so para voce reconhecer a chave depois
              </p>
            </div>
            <Button type="submit" disabled={criando}>
              {criando ? "Criando..." : "Criar chave"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Chaves</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader className="bg-muted/50">
              <TableRow>
                <TableHead>Nome</TableHead>
                <TableHead>Chave</TableHead>
                <TableHead>Criada</TableHead>
                <TableHead>Ultimo uso</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Acoes</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {chaves.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                    Nenhuma chave criada
                  </TableCell>
                </TableRow>
              )}
              {chaves.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>{c.nome}</TableCell>
                  <TableCell className="font-mono text-xs">{c.prefixo}...</TableCell>
                  <TableCell className="text-xs">{formatarData(c.criada_em)}</TableCell>
                  <TableCell className="text-xs">{formatarData(c.ultimo_uso_em)}</TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className={
                        c.ativa
                          ? "bg-green-100 text-green-800"
                          : "bg-neutral-200 text-neutral-600"
                      }
                    >
                      {c.ativa ? "Ativa" : "Revogada"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    {c.ativa && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-red-600 hover:text-red-700"
                        onClick={() => setRevogando(c)}
                      >
                        Revogar
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Conectar um LLM (MCP)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <p className="text-muted-foreground">
            O sistema expoe um servidor MCP. Com ele, um assistente consegue emitir,
            consultar e cancelar notas conversando com voce. Use uma chave desta tela
            como token de autenticacao.
          </p>

          <div className="space-y-2">
            <Label>Endereco do servidor</Label>
            <div className="flex gap-2">
              <Input readOnly value={urlMcp} className="font-mono text-xs" />
              <Button variant="outline" onClick={() => copiar(urlMcp, "Endereco")}>
                Copiar
              </Button>
            </div>
          </div>

          <div className="space-y-2">
            <Label>Configuracao para clientes que usam arquivo JSON</Label>
            <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
{`{
  "mcpServers": {
    "nfse": {
      "type": "http",
      "url": "${urlMcp}",
      "headers": {
        "Authorization": "Bearer SUA_CHAVE_AQUI"
      }
    }
  }
}`}
            </pre>
          </div>

          <div className="space-y-1">
            <p className="font-medium">Ferramentas disponiveis</p>
            <ul className="list-inside list-disc text-muted-foreground">
              <li>consultar_configuracao: prestador, leiaute e se o modo teste esta ativo</li>
              <li>listar_notas e consultar_nota: consulta, com link do PDF</li>
              <li>emitir_nota: emite (ou so valida, no modo teste)</li>
              <li>cancelar_nota: cancela na prefeitura</li>
              <li>sincronizar_notas: puxa notas emitidas fora do sistema</li>
            </ul>
          </div>

          <Alert>
            <AlertTitle>Com o modo teste desligado, o assistente emite nota real</AlertTitle>
            <AlertDescription>
              As ferramentas avisam o modelo disso, mas quem decide e voce: prefira
              deixar o modo teste ativo enquanto estiver experimentando.
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>

      <Dialog open={novaChave !== null} onOpenChange={(v) => !v && setNovaChave(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Chave criada</DialogTitle>
            <DialogDescription>
              Copie agora: esta e a unica vez que a chave aparece. O sistema guarda
              apenas um hash dela.
            </DialogDescription>
          </DialogHeader>
          <div className="flex gap-2">
            <Input readOnly value={novaChave ?? ""} className="font-mono text-xs" />
            <Button onClick={() => novaChave && copiar(novaChave, "Chave")}>
              Copiar
            </Button>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setNovaChave(null)}>
              Ja copiei
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={revogando !== null} onOpenChange={(v) => !v && setRevogando(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revogar {revogando?.nome}</DialogTitle>
            <DialogDescription>
              Qualquer integracao que use esta chave para de funcionar na hora, na API
              e no MCP. Nao da para reativar.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRevogando(null)}>
              Voltar
            </Button>
            <Button variant="destructive" onClick={confirmarRevogacao}>
              Revogar chave
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
