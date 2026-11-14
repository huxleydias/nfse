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
import { api, ApiError, type Config, ehNacional, type Nota } from "@/lib/api"
import {
  documentoValido,
  ehCnpj as docEhCnpj,
  mascaraCep,
  mascaraCpfCnpj,
  mascaraMoeda,
  moedaParaNumero,
  soDigitos,
} from "@/lib/mascaras"

export default function Emitir() {
  const navigate = useNavigate()
  const [cfg, setCfg] = useState<Config | null>(null)
  const [enviando, setEnviando] = useState(false)
  const [emitida, setEmitida] = useState<Nota | null>(null)

  const [doc, setDoc] = useState("")
  const [nome, setNome] = useState("")
  const [email, setEmail] = useState("")
  const [servico, setServico] = useState("")
  const [valor, setValor] = useState("")
  const [descricao, setDescricao] = useState("")
  // Nacional: data de competencia (vazio = hoje)
  const [competencia, setCompetencia] = useState("")

  const [cep, setCep] = useState("")
  const [logradouro, setLogradouro] = useState("")
  const [numero, setNumero] = useState("")
  const [complemento, setComplemento] = useState("")
  const [bairro, setBairro] = useState("")
  const [codigoMunicipio, setCodigoMunicipio] = useState("")
  const [uf, setUf] = useState("")

  const ehCnpj = docEhCnpj(doc)
  const docCompleto = soDigitos(doc).length === 11 || soDigitos(doc).length === 14
  const docInvalido = docCompleto && !documentoValido(doc)
  const valorNumerico = moedaParaNumero(valor)

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
    const limpo = soDigitos(cep)
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
    if (docInvalido) {
      toast.error("CPF ou CNPJ do tomador invalido")
      return
    }
    if (valorNumerico <= 0) {
      toast.error("Informe o valor da nota")
      return
    }
    setEnviando(true)
    try {
      const payload: Record<string, unknown> = {
        tomador: {
          cpf_cnpj: soDigitos(doc),
          razao_social: nome,
          email,
          ...(ehCnpj && logradouro
            ? {
                endereco: {
                  cep: soDigitos(cep),
                  logradouro,
                  numero,
                  complemento,
                  bairro,
                  codigo_municipio: soDigitos(codigoMunicipio),
                  uf,
                },
              }
            : {}),
        },
        servico,
        valor: valorNumerico,
        descricao,
        ...(cfg?.ambiente === "nacional" && competencia ? { competencia } : {}),
      }
      const r = await api.emitirNota(payload)
      if (r.teste && !r.nota) {
        toast.success("Modo teste: pedido validado pela prefeitura, nenhuma nota emitida")
      } else if (r.nota) {
        toast.success(
          r.teste
            ? `NFS-e ${r.nota.numero_nfse} emitida na producao restrita (sem valor fiscal)`
            : `NFS-e ${r.nota.numero_nfse} emitida`,
        )
        for (const alerta of r.alertas ?? []) {
          toast.warning(`[${alerta.codigo}] ${alerta.descricao}`, { duration: 12000 })
        }
        setEmitida(r.nota)
      }
    } catch (err) {
      if (err instanceof ApiError) {
        const d = err.detail as {
          erros_prefeitura?: { codigo: string; descricao: string }[]
          xsd?: string[]
        }
        if (d && typeof d === "object" && d.erros_prefeitura) {
          toast.error(
            d.erros_prefeitura.map((e2) => `[${e2.codigo}] ${e2.descricao}`).join("; "),
          )
        } else if (d && typeof d === "object" && d.xsd) {
          toast.error(`Campo fiscal invalido: ${d.xsd.join("; ")}`, { duration: 12000 })
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

  function novaEmissao() {
    setEmitida(null)
    setDoc("")
    setNome("")
    setEmail("")
    setValor("")
    setCep("")
    setLogradouro("")
    setNumero("")
    setComplemento("")
    setBairro("")
    setCodigoMunicipio("")
    setUf("")
    setCompetencia("")
  }

  if (emitida && ehNacional(emitida)) {
    return (
      <div className="mx-auto w-full max-w-3xl space-y-6">
        <h1 className="text-2xl font-bold">Nota emitida</h1>

        <Alert className="border-green-300 bg-green-50 text-green-900">
          <AlertTitle>
            NFS-e {emitida.numero_nfse} autorizada no Sistema Nacional
            {emitida.ambiente === "nacional_homologacao" ? " (producao restrita)" : ""}
          </AlertTitle>
          <AlertDescription>
            {emitida.tomador_nome}:{" "}
            {emitida.valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}.
            Chave de acesso {emitida.chave_acesso}
          </AlertDescription>
        </Alert>

        <div className="flex flex-wrap gap-2">
          {emitida.pdf_url && (
            <Button asChild>
              <a href={emitida.pdf_url} target="_blank" rel="noreferrer">
                Abrir nota oficial
              </a>
            </Button>
          )}
          <Button variant="outline" onClick={novaEmissao}>
            Emitir outra
          </Button>
          <Button variant="ghost" onClick={() => navigate("/notas")}>
            Ver todas as notas
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          O PDF oficial (DANFSe) e baixado na Consulta Publica do Sistema Nacional, pela
          chave de acesso.
        </p>
      </div>
    )
  }

  if (emitida) {
    return (
      <div className="mx-auto w-full max-w-3xl space-y-6">
        <h1 className="text-2xl font-bold">Nota emitida</h1>

        <Alert className="border-green-300 bg-green-50 text-green-900">
          <AlertTitle>NFS-e {emitida.numero_nfse} autorizada</AlertTitle>
          <AlertDescription>
            {emitida.tomador_nome} - {emitida.valor.toLocaleString("pt-BR", {
              style: "currency",
              currency: "BRL",
            })}
            {emitida.codigo_verificacao
              ? ` - codigo de verificacao ${emitida.codigo_verificacao}`
              : ""}
          </AlertDescription>
        </Alert>

        <div className="flex flex-wrap gap-2">
          <Button asChild>
            <a href={api.urlPdf(emitida.id, true)} download>
              Baixar PDF
            </a>
          </Button>
          <Button variant="outline" asChild>
            <a href={api.urlPdf(emitida.id)} target="_blank" rel="noreferrer">
              Abrir em nova aba
            </a>
          </Button>
          <Button variant="outline" onClick={novaEmissao}>
            Emitir outra
          </Button>
          <Button variant="ghost" onClick={() => navigate("/notas")}>
            Ver todas as notas
          </Button>
        </div>

        <Card className="overflow-hidden p-0">
          <iframe
            src={api.urlPdf(emitida.id)}
            title={`NFS-e ${emitida.numero_nfse}`}
            className="h-[800px] w-full border-0"
          />
        </Card>
        <p className="text-xs text-muted-foreground">
          PDF oficial gerado pela Prefeitura de Sao Paulo a partir do numero da nota e
          do codigo de verificacao.
        </p>
      </div>
    )
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6">
      <h1 className="text-2xl font-bold">Emitir nota</h1>

      {cfg?.modo_teste && (
        <Alert className="border-amber-300 bg-amber-50 text-amber-900">
          <AlertTitle>Modo teste ativo</AlertTitle>
          <AlertDescription>
            {cfg.ambiente === "nacional"
              ? "A nota sai na producao restrita do Sistema Nacional, sem valor fiscal."
              : "A emissao valida tudo na prefeitura mas NAO gera nota real."}{" "}
            Desative na Configuracao quando estiver pronto.
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
              <Input
                id="doc"
                value={doc}
                onChange={(e) => setDoc(mascaraCpfCnpj(e.target.value))}
                placeholder="000.000.000-00"
                inputMode="numeric"
                aria-invalid={docInvalido}
                required
              />
              <p className={`text-xs ${docInvalido ? "text-red-600" : "text-muted-foreground"}`}>
                {docInvalido
                  ? "Digitos conferem o formato mas o documento e invalido"
                  : "So numeros; a pontuacao entra sozinha"}
              </p>
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
                  <Input
                    id="cep"
                    value={cep}
                    onChange={(e) => setCep(mascaraCep(e.target.value))}
                    onBlur={buscarCep}
                    placeholder="00000-000"
                    inputMode="numeric"
                  />
                  <p className="text-xs text-muted-foreground">
                    Preenche o endereco sozinho ao sair do campo
                  </p>
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
                    <Input
                      id="municipio"
                      value={codigoMunicipio}
                      onChange={(e) => setCodigoMunicipio(soDigitos(e.target.value).slice(0, 7))}
                      placeholder="3550308"
                      inputMode="numeric"
                    />
                    <p className="text-xs text-muted-foreground">IBGE, 7 digitos</p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="uf">UF</Label>
                    <Input
                      id="uf"
                      value={uf}
                      maxLength={2}
                      onChange={(e) => setUf(e.target.value.toUpperCase().replace(/[^A-Z]/g, ""))}
                    />
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
                <SelectTrigger className="w-full">
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
              {cfg && servico && cfg.servicos[servico] && (
                <p className="text-xs text-muted-foreground">
                  ISS {(cfg.servicos[servico].aliquota * 100).toLocaleString("pt-BR", {
                    minimumFractionDigits: 2,
                  })}
                  %
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="valor">Valor da nota</Label>
              <div className="relative">
                <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                  R$
                </span>
                <Input
                  id="valor"
                  className="pl-9 text-right tabular-nums"
                  inputMode="numeric"
                  value={valor}
                  onChange={(e) => setValor(mascaraMoeda(e.target.value))}
                  placeholder="0,00"
                  required
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Digite so os numeros: 59900 vira 599,00. Os centavos sao as duas
                ultimas casas
              </p>
            </div>
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="descricao">Descricao (discriminacao na nota)</Label>
              <Textarea
                id="descricao"
                value={descricao}
                onChange={(e) => setDescricao(e.target.value)}
                rows={3}
                maxLength={2000}
                required
              />
              <p className="text-xs text-muted-foreground">
                {descricao.length}/2000 caracteres
              </p>
            </div>
            {cfg?.ambiente === "nacional" && (
              <div className="space-y-2">
                <Label htmlFor="competencia">Competencia</Label>
                <Input
                  id="competencia"
                  type="date"
                  value={competencia}
                  max={new Date().toISOString().slice(0, 10)}
                  onChange={(e) => setCompetencia(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Data em que o servico foi prestado. Vazio usa hoje
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        <Button type="submit" disabled={enviando || !cfg}>
          {enviando ? "Emitindo..." : cfg?.modo_teste ? "Testar emissao" : "Emitir nota"}
        </Button>
      </form>
    </div>
  )
}
