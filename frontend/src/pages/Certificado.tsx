import { useEffect, useState } from "react"
import { toast } from "sonner"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api, ApiError, type CertificadoMeta } from "@/lib/api"

export default function Certificado() {
  const [meta, setMeta] = useState<CertificadoMeta | null>(null)
  const [arquivo, setArquivo] = useState<File | null>(null)
  const [senha, setSenha] = useState("")
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    api.statusCertificado().then((r) => setMeta(r.certificado))
  }, [])

  async function enviar(e: React.FormEvent) {
    e.preventDefault()
    if (!arquivo) return
    setEnviando(true)
    try {
      const r = await api.enviarCertificado(arquivo, senha)
      setMeta(r.certificado)
      setSenha("")
      setArquivo(null)
      toast.success("Certificado salvo")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Falha no upload")
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="max-w-xl space-y-4">
      <h1 className="text-2xl font-bold">Certificado digital A1</h1>

      {meta ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Certificado atual</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <p>
              <span className="text-muted-foreground">Titular:</span> {meta.cn}
            </p>
            <p>
              <span className="text-muted-foreground">Emissor:</span> {meta.emissor}
            </p>
            <p>
              <span className="text-muted-foreground">Valido ate:</span>{" "}
              {new Date(meta.valido_ate).toLocaleDateString("pt-BR")} ({meta.dias_restantes}{" "}
              dias)
            </p>
          </CardContent>
        </Card>
      ) : (
        <Alert>
          <AlertTitle>Nenhum certificado configurado</AlertTitle>
          <AlertDescription>
            Envie o arquivo .pfx do certificado A1 da empresa para habilitar a emissao.
          </AlertDescription>
        </Alert>
      )}

      {meta && meta.vencido && (
        <Alert variant="destructive">
          <AlertTitle>Certificado vencido</AlertTitle>
          <AlertDescription>Emissao bloqueada. Envie um certificado valido.</AlertDescription>
        </Alert>
      )}
      {meta && !meta.vencido && meta.dias_restantes < 30 && (
        <Alert className="border-amber-300 bg-amber-50 text-amber-900">
          <AlertTitle>Certificado vence em {meta.dias_restantes} dias</AlertTitle>
          <AlertDescription>
            Renove o A1 e envie o novo .pfx aqui. Aproveite para trocar a senha.
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Enviar novo certificado</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={enviar} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="pfx">Arquivo .pfx</Label>
              <Input
                id="pfx"
                type="file"
                accept=".pfx,.p12"
                onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="senha-cert">Senha do certificado</Label>
              <Input
                id="senha-cert"
                type="password"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                required
              />
              <p className="text-xs text-muted-foreground">
                A senha e validada, cifrada e armazenada no servidor. Nao aparece em logs.
              </p>
            </div>
            <Button type="submit" disabled={enviando || !arquivo}>
              {enviando ? "Validando..." : "Salvar certificado"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
