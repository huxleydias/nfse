import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { api, ApiError, type Nota } from "@/lib/api"

const BADGES: Record<string, { label: string; classe: string }> = {
  autorizada: { label: "Autorizada", classe: "bg-green-100 text-green-800" },
  cancelada: { label: "Cancelada", classe: "bg-neutral-200 text-neutral-600" },
  erro: { label: "Erro", classe: "bg-red-100 text-red-800" },
  processando: { label: "Processando", classe: "bg-amber-100 text-amber-800" },
}

function formatarValor(v: number) {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
}

function formatarData(iso: string) {
  return new Date(iso).toLocaleDateString("pt-BR")
}

export default function Notas() {
  const [notas, setNotas] = useState<Nota[]>([])
  const [status, setStatus] = useState("todas")
  const [inicio, setInicio] = useState("")
  const [fim, setFim] = useState("")
  const [detalhe, setDetalhe] = useState<Nota | null>(null)
  const [cancelando, setCancelando] = useState<Nota | null>(null)
  const [sincronizando, setSincronizando] = useState(false)

  const carregar = useCallback(async () => {
    try {
      const r = await api.listarNotas({
        inicio: inicio || undefined,
        fim: fim || undefined,
        status: status === "todas" ? undefined : status,
      })
      setNotas(r.notas)
    } catch {
      toast.error("Falha ao carregar notas")
    }
  }, [inicio, fim, status])

  useEffect(() => {
    carregar()
  }, [carregar])

  async function sincronizar() {
    setSincronizando(true)
    try {
      const hoje = new Date()
      const inicioMes = new Date(hoje.getFullYear(), hoje.getMonth() - 2, 1)
      const r = await api.sincronizar(
        inicioMes.toISOString().slice(0, 10),
        hoje.toISOString().slice(0, 10),
      )
      toast.success(`Sincronizado: ${r.novas} novas, ${r.atualizadas} atualizadas`)
      carregar()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Falha na sincronizacao")
    } finally {
      setSincronizando(false)
    }
  }

  async function confirmarCancelamento() {
    if (!cancelando) return
    try {
      await api.cancelarNota(cancelando.id)
      toast.success(`Nota ${cancelando.numero_nfse} cancelada`)
      setCancelando(null)
      carregar()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Falha ao cancelar")
    }
  }

  async function abrirDetalhe(nota: Nota) {
    try {
      const r = await api.detalheNota(nota.id)
      setDetalhe(r.nota)
    } catch {
      toast.error("Falha ao carregar detalhe")
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Notas fiscais</h1>
        <Button onClick={sincronizar} disabled={sincronizando} variant="outline">
          {sincronizando ? "Sincronizando..." : "Sincronizar com a prefeitura"}
        </Button>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="text-xs text-muted-foreground">Inicio</label>
          <Input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} />
        </div>
        <div>
          <label className="text-xs text-muted-foreground">Fim</label>
          <Input type="date" value={fim} onChange={(e) => setFim(e.target.value)} />
        </div>
        <div className="w-40">
          <label className="text-xs text-muted-foreground">Status</label>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="todas">Todas</SelectItem>
              <SelectItem value="autorizada">Autorizadas</SelectItem>
              <SelectItem value="cancelada">Canceladas</SelectItem>
              <SelectItem value="erro">Com erro</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Data</TableHead>
            <TableHead>NFS-e</TableHead>
            <TableHead>Tomador</TableHead>
            <TableHead>Valor</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Acoes</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {notas.length === 0 && (
            <TableRow>
              <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                Nenhuma nota encontrada
              </TableCell>
            </TableRow>
          )}
          {notas.map((n) => {
            const badge = BADGES[n.status] ?? { label: n.status, classe: "" }
            return (
              <TableRow key={n.id}>
                <TableCell>{formatarData(n.criada_em)}</TableCell>
                <TableCell>{n.numero_nfse ?? "..."}</TableCell>
                <TableCell>{n.tomador_nome ?? n.tomador_doc}</TableCell>
                <TableCell>{formatarValor(n.valor)}</TableCell>
                <TableCell>
                  <Badge variant="outline" className={badge.classe}>
                    {badge.label}
                  </Badge>
                </TableCell>
                <TableCell className="space-x-2 text-right">
                  <Button variant="ghost" size="sm" onClick={() => abrirDetalhe(n)}>
                    Detalhe
                  </Button>
                  {n.status === "autorizada" && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-red-600 hover:text-red-700"
                      onClick={() => setCancelando(n)}
                    >
                      Cancelar
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>

      <Dialog open={cancelando !== null} onOpenChange={(v) => !v && setCancelando(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancelar NFS-e {cancelando?.numero_nfse}</DialogTitle>
            <DialogDescription>
              O cancelamento e feito na prefeitura e nao pode ser desfeito. Tomador:{" "}
              {cancelando?.tomador_nome}, valor{" "}
              {cancelando ? formatarValor(cancelando.valor) : ""}.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelando(null)}>
              Voltar
            </Button>
            <Button variant="destructive" onClick={confirmarCancelamento}>
              Cancelar nota
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={detalhe !== null} onOpenChange={(v) => !v && setDetalhe(null)}>
        <DialogContent className="max-h-[80vh] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {detalhe?.numero_nfse
                ? `NFS-e ${detalhe.numero_nfse}`
                : `RPS ${detalhe?.serie_rps} ${detalhe?.numero_rps}`}
            </DialogTitle>
            <DialogDescription>
              {detalhe?.tomador_nome} ({detalhe?.tomador_doc}),{" "}
              {detalhe ? formatarValor(detalhe.valor) : ""}
              {detalhe?.codigo_verificacao
                ? `, verificacao ${detalhe.codigo_verificacao}`
                : ""}
            </DialogDescription>
          </DialogHeader>
          {detalhe?.erros_json && (
            <pre className="overflow-x-auto rounded bg-red-50 p-3 text-xs text-red-800">
              {JSON.stringify(JSON.parse(detalhe.erros_json), null, 2)}
            </pre>
          )}
          {detalhe?.xml_enviado && (
            <details>
              <summary className="cursor-pointer text-sm font-medium">XML enviado</summary>
              <pre className="mt-2 max-h-64 overflow-auto rounded bg-muted p-3 text-xs">
                {detalhe.xml_enviado}
              </pre>
            </details>
          )}
          {detalhe?.xml_retorno && (
            <details>
              <summary className="cursor-pointer text-sm font-medium">XML retorno</summary>
              <pre className="mt-2 max-h-64 overflow-auto rounded bg-muted p-3 text-xs">
                {detalhe.xml_retorno}
              </pre>
            </details>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
