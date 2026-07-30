import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { api, ApiError, type Config } from "@/lib/api"

export default function Emitir() {
  const navigate = useNavigate()
  const [cfg, setCfg] = useState<Config | null>(null)
  const [enviando, setEnviando] = useState(false)

  const [doc, setDoc] = useState("")
  const [nome, setNome] = useState("")
  const [email, setEmail] = useState("")
  const [servico, setServico] = useState("")
  const [valor, setValor] = useState("")
  const [descricao, setDescricao] = useState("")

  const [cep, setCep] = useState("")
  const [logradouro, setLogradouro] = useState("")
  const [numero, setNumero] = useState("")
  const [complemento, setComplemento] = useState("")
  const [bairro, setBairro] = useState("")
  const [codigoMunicipio, setCodigoMunicipio] = useState("")
  const [uf, setUf] = useState("")

  const ehCnpj = doc.replace(/\D/g, "").length > 11

  useEffect(() => {
    api.obterConfig().then((c) => {
      setCfg(c)
      const codigos = Object.keys(c.servicos)
      if (codigos.length > 0) setServico(codigos[0])
    })
  }, [])

  useEffect(() => {
    if (cfg && servico && cfg.servicos[servico] && !descricao) {
      setDescricao(cfg.servicos[servico].descricao_padrao)
    }
  }, [cfg, servico, descricao])

  async function buscarCep() {
    const limpo = cep.replace(/\D/g, "")
    if (limpo.length !== 8) return
    try {
      const r = await fetch(`https://viacep.com.br/ws/${limpo}/json/`)
      const d = await r.json()
      if (d.erro) return
      setLogradouro(d.logradouro ?? "")
      setBairro(d.bairro ?? "")
      setCodigoMunicipio(d.ibge ?? "")
      setUf(d.uf ?? "")
    } catch {
      // CEP e conveniencia; falha silenciosa nao bloqueia emissao
    }
  }

  async function emitir(e: React.FormEvent) {
    e.preventDefault()
    setEnviando(true)
    try {
      const payload: Record<string, unknown> = {
        tomador: {
          cpf_cnpj: doc,
          razao_social: nome,
          email,
          ...(ehCnpj && logradouro
            ? {
                endereco: {
                  cep,
                  logradouro,
                  numero,
                  complemento,
                  bairro,
                  codigo_municipio: codigoMunicipio,
                  uf,
                },
              }
            : {}),
        },
        servico,
        valor: parseFloat(valor.replace(",", ".")),
        descricao,
      }
      const r = await api.emitirNota(payload)
      if (r.teste) {
        toast.success("Modo teste: pedido validado pela prefeitura, nenhuma nota emitida")
      } else {
        toast.success(`NFS-e ${r.nota?.numero_nfse} emitida`)
        navigate("/notas")
      }
    } catch (err) {
      if (err instanceof ApiError) {
        const d = err.detail as { erros_prefeitura?: { codigo: string; descricao: string }[] }
        if (d && typeof d === "object" && d.erros_prefeitura) {
          toast.error(
            d.erros_prefeitura.map((e2) => `[${e2.codigo}] ${e2.descricao}`).join("; "),
          )
        } else {
          toast.error(err.message)
        }
      } else {
        toast.error("Falha na emissao")
      }
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="max-w-2xl space-y-4">
      <h1 className="text-2xl font-bold">Emitir nota</h1>

      {cfg?.modo_teste && (
        <Alert className="border-amber-300 bg-amber-50 text-amber-900">
          <AlertTitle>Modo teste ativo</AlertTitle>
          <AlertDescription>
            A emissao valida tudo na prefeitura mas NAO gera nota real. Desative na
            Configuracao quando estiver pronto.
          </AlertDescription>
        </Alert>
      )}

      <form onSubmit={emitir} className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Tomador</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="doc">CPF ou CNPJ</Label>
              <Input id="doc" value={doc} onChange={(e) => setDoc(e.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="nome">Nome / Razao social</Label>
              <Input id="nome" value={nome} onChange={(e) => setNome(e.target.value)} required />
            </div>
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="email">E-mail (recebe a nota)</Label>
              <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>

            {ehCnpj && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="cep">CEP</Label>
                  <Input id="cep" value={cep} onChange={(e) => setCep(e.target.value)} onBlur={buscarCep} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="logradouro">Logradouro</Label>
                  <Input id="logradouro" value={logradouro} onChange={(e) => setLogradouro(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="numero">Numero</Label>
                  <Input id="numero" value={numero} onChange={(e) => setNumero(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="complemento">Complemento</Label>
                  <Input id="complemento" value={complemento} onChange={(e) => setComplemento(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="bairro">Bairro</Label>
                  <Input id="bairro" value={bairro} onChange={(e) => setBairro(e.target.value)} />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="municipio">Cod. municipio</Label>
                    <Input id="municipio" value={codigoMunicipio} onChange={(e) => setCodigoMunicipio(e.target.value)} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="uf">UF</Label>
                    <Input id="uf" value={uf} maxLength={2} onChange={(e) => setUf(e.target.value)} />
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Servico</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Codigo de servico</Label>
              <Select value={servico} onValueChange={setServico}>
                <SelectTrigger>
                  <SelectValue placeholder="Selecione" />
                </SelectTrigger>
                <SelectContent>
                  {cfg &&
                    Object.entries(cfg.servicos).map(([codigo, s]) => (
                      <SelectItem key={codigo} value={codigo}>
                        {codigo}: {s.descricao_padrao.slice(0, 40)}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="valor">Valor (R$)</Label>
              <Input
                id="valor"
                inputMode="decimal"
                value={valor}
                onChange={(e) => setValor(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="descricao">Descricao (discriminacao na nota)</Label>
              <Textarea
                id="descricao"
                value={descricao}
                onChange={(e) => setDescricao(e.target.value)}
                rows={3}
                required
              />
            </div>
          </CardContent>
        </Card>

        <Button type="submit" disabled={enviando || !cfg}>
          {enviando ? "Emitindo..." : cfg?.modo_teste ? "Testar emissao" : "Emitir nota"}
        </Button>
      </form>
    </div>
  )
}
