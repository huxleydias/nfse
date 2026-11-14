import { useEffect, useState } from "react"
import { toast } from "sonner"
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
import { Separator } from "@/components/ui/separator"
import { Switch } from "@/components/ui/switch"
import {
  api,
  ApiError,
  type Config as ConfigT,
  type NacionalConfig,
  type ServicoConfig,
} from "@/lib/api"
import {
  completarCodigo,
  documentoValido,
  fracaoParaPercentual,
  mascaraCodigo,
  mascaraCpfCnpj,
  percentualParaFracao,
  soDigitos,
} from "@/lib/mascaras"

const SERVICO_VAZIO: ServicoConfig = {
  descricao_padrao: "",
  aliquota: 0.02,
  iss_retido: false,
  nbs: "",
  c_class_trib: "",
  c_ind_op: "",
  fin_nfse: 0,
  ind_final: 1,
  ind_dest: 0,
  c_loc_prestacao: "3550308",
  c_trib_nac: "",
  c_nbs: "",
}

export default function Config() {
  const [cfg, setCfg] = useState<ConfigT | null>(null)
  const [salvando, setSalvando] = useState(false)
  const [novoCodigo, setNovoCodigo] = useState("")
  // Texto do percentual enquanto digita: o numero sozinho perderia "6," no meio
  const [pTotTexto, setPTotTexto] = useState<string | null>(null)

  useEffect(() => {
    api.obterConfig().then(setCfg)
  }, [])

  if (!cfg) return <p className="text-muted-foreground">Carregando...</p>

  function setPrestador(campo: string, valor: string) {
    setCfg((c) => c && { ...c, prestador: { ...c.prestador, [campo]: valor } })
  }

  function setNacional<K extends keyof NacionalConfig>(campo: K, valor: NacionalConfig[K]) {
    setCfg((c) => c && { ...c, nacional: { ...c.nacional, [campo]: valor } })
  }

  const nacional = cfg.ambiente === "nacional"

  function setServico(codigo: string, campo: keyof ServicoConfig, valor: unknown) {
    setCfg(
      (c) =>
        c && {
          ...c,
          servicos: {
            ...c.servicos,
            [codigo]: { ...c.servicos[codigo], [campo]: valor },
          },
        },
    )
  }

  function adicionarServico() {
    const codigo = novoCodigo.replace(/\D/g, "")
    if (codigo.length < 4) {
      toast.error("Informe o codigo de servico municipal (4 ou 5 digitos)")
      return
    }
    setCfg((c) => c && { ...c, servicos: { ...c.servicos, [codigo]: { ...SERVICO_VAZIO } } })
    setNovoCodigo("")
  }

  function removerServico(codigo: string) {
    setCfg((c) => {
      if (!c) return c
      const servicos = { ...c.servicos }
      delete servicos[codigo]
      return { ...c, servicos }
    })
  }

  async function salvar() {
    if (!cfg) return
    setSalvando(true)
    try {
      const salvo = await api.salvarConfig(cfg)
      setCfg(salvo)
      toast.success("Configuracao salva")
    } catch (err) {
      const detalhe = err instanceof ApiError && Array.isArray(err.detail)
        ? `: ${(err.detail as string[]).join("; ")}`
        : ""
      toast.error(`Falha ao salvar${detalhe}`, { duration: 10000 })
    } finally {
      setSalvando(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Configuracao</h1>
        <Button onClick={salvar} disabled={salvando}>
          {salvando ? "Salvando..." : "Salvar tudo"}
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Ambiente de emissao</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Select
            value={cfg.ambiente}
            onValueChange={(v) => setCfg({ ...cfg, ambiente: v as ConfigT["ambiente"] })}
          >
            <SelectTrigger className="w-full sm:w-96">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="municipal">Municipal: webservice da Prefeitura de SP</SelectItem>
              <SelectItem value="nacional">Nacional: Sistema Nacional NFS-e (Sefin)</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-sm text-muted-foreground">
            ME e EPP do Simples Nacional emitem so no Sistema Nacional para competencias
            a partir de 01/11/2026 (Resolucao CGSN 191/2026). Regime Normal continua no
            municipal. Notas antigas sempre cancelam no ambiente em que sairam.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Modo de operacao</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center gap-3">
          <Switch
            checked={cfg.modo_teste}
            onCheckedChange={(v) => setCfg({ ...cfg, modo_teste: v })}
          />
          <div>
            <p className="font-medium">Modo teste {cfg.modo_teste ? "ativo" : "desligado"}</p>
            <p className="text-sm text-muted-foreground">
              {nacional
                ? "Ativo: emite na producao restrita do Sistema Nacional, sem valor fiscal. Desligado: emite nota REAL."
                : "Ativo: valida na prefeitura sem emitir nota. Desligado: emite nota REAL."}
            </p>
          </div>
        </CardContent>
      </Card>

      {nacional && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Sistema Nacional</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Percentual aproximado de tributos do Simples</Label>
              <div className="relative">
                <Input
                  className="pr-8 text-right tabular-nums"
                  inputMode="decimal"
                  value={
                    pTotTexto ??
                    (cfg.nacional.p_tot_trib_sn == null
                      ? ""
                      : String(cfg.nacional.p_tot_trib_sn).replace(".", ","))
                  }
                  placeholder="0,00"
                  onChange={(e) => {
                    const texto = e.target.value.replace(/[^\d,]/g, "")
                    setPTotTexto(texto)
                    const numero = Number(texto.replace(",", "."))
                    setNacional(
                      "p_tot_trib_sn",
                      texto === "" || Number.isNaN(numero) ? null : numero,
                    )
                  }}
                  onBlur={() => setPTotTexto(null)}
                />
                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                  %
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                Obrigatorio para ME/EPP (campo pTotTribSN). Confirme com o contador. Sem
                valor, a emissao e recusada antes de enviar.
              </p>
            </div>
            <div className="space-y-2">
              <Label>Apuracao dos tributos</Label>
              <Select
                value={String(cfg.nacional.reg_ap_trib_sn)}
                onValueChange={(v) => setNacional("reg_ap_trib_sn", Number(v))}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">1: federais e ISSQN pelo Simples</SelectItem>
                  <SelectItem value="2">2: federais pelo Simples, ISSQN por fora</SelectItem>
                  <SelectItem value="3">3: federais e ISSQN por fora do Simples</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Emissao implementada para ME/EPP do Simples (situacao 3).
              </p>
            </div>
            <div className="space-y-2">
              <Label>Serie da DPS</Label>
              <Input
                className="tabular-nums"
                inputMode="numeric"
                value={cfg.nacional.serie_dps}
                onChange={(e) => setNacional("serie_dps", mascaraCodigo(e.target.value, 5))}
              />
              <p className="text-xs text-muted-foreground">
                Numero de 1 a 49999 (faixa de sistema proprio)
              </p>
            </div>
            <div className="space-y-2">
              <Label>Proximo numero da DPS</Label>
              <Input
                type="number"
                value={cfg.nacional.proximo_numero_dps}
                onChange={(e) =>
                  setNacional("proximo_numero_dps", parseInt(e.target.value || "1"))
                }
              />
              <p className="text-xs text-muted-foreground">
                So avanca. Homologacao tem contador proprio (proximo:{" "}
                {cfg.nacional.proximo_numero_dps_homologacao}).
              </p>
            </div>
            <div className="space-y-2">
              <Label>Municipio emissor (IBGE)</Label>
              <Input
                className="tabular-nums"
                inputMode="numeric"
                value={cfg.nacional.c_loc_emi}
                onChange={(e) => setNacional("c_loc_emi", mascaraCodigo(e.target.value, 7))}
              />
              <p className="text-xs text-muted-foreground">7 digitos. Sao Paulo e 3550308</p>
            </div>
            <div className="flex items-center gap-2 pt-5">
              <Switch
                checked={cfg.nacional.informar_im}
                onCheckedChange={(v) => setNacional("informar_im", v)}
              />
              <div>
                <Label>Informar inscricao municipal na DPS</Label>
                <p className="text-xs text-muted-foreground">
                  Desligue se o Sistema Nacional recusar a IM do prestador.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Layout do XML</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-3">
            <Switch
              checked={cfg.layout === 2}
              onCheckedChange={(v) => setCfg({ ...cfg, layout: v ? 2 : 1 })}
            />
            <div>
              <p className="font-medium">
                Layout {cfg.layout === 2 ? "2 (reforma IBS/CBS)" : "1 (pre reforma)"}
              </p>
              <p className="text-sm text-muted-foreground">
                Optantes do Simples Nacional e MEI usam o layout 1 ate 04/01/2027.
                Empresas do Regime Normal usam o layout 2 desde 03/08/2026. Enviar o
                layout errado para o regime faz a prefeitura recusar a nota.
              </p>
            </div>
          </div>
          {cfg.layout === 1 && (
            <p className="text-xs text-muted-foreground">
              No layout 1 os campos NBS, cClassTrib e cIndOp abaixo ficam guardados mas
              nao vao no XML.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Prestador</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label>CNPJ</Label>
            <Input
              value={mascaraCpfCnpj(cfg.prestador.cnpj)}
              onChange={(e) => setPrestador("cnpj", mascaraCpfCnpj(e.target.value))}
              placeholder="00.000.000/0000-00"
              inputMode="numeric"
              aria-invalid={
                soDigitos(cfg.prestador.cnpj).length === 14 &&
                !documentoValido(cfg.prestador.cnpj)
              }
            />
            <p className="text-xs text-muted-foreground">
              So numeros; a pontuacao entra sozinha
            </p>
          </div>
          <div className="space-y-2">
            <Label>Inscricao municipal (CCM)</Label>
            <Input
              value={cfg.prestador.inscricao_municipal}
              onChange={(e) =>
                setPrestador("inscricao_municipal", mascaraCodigo(e.target.value, 12))
              }
              placeholder="12345678"
              inputMode="numeric"
            />
            <p className="text-xs text-muted-foreground">So digitos, ate 12</p>
          </div>
          <div className="space-y-2">
            <Label>Razao social</Label>
            <Input
              value={cfg.prestador.razao_social}
              onChange={(e) => setPrestador("razao_social", e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label>E-mail</Label>
            <Input value={cfg.prestador.email} onChange={(e) => setPrestador("email", e.target.value)} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">RPS</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Serie</Label>
            <Input
              value={cfg.serie_rps}
              maxLength={5}
              onChange={(e) => setCfg({ ...cfg, serie_rps: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label>Proximo numero</Label>
            <Input
              type="number"
              value={cfg.proximo_numero_rps}
              onChange={(e) =>
                setCfg({ ...cfg, proximo_numero_rps: parseInt(e.target.value || "1") })
              }
            />
            <p className="text-xs text-muted-foreground">
              Nunca reutilize numero de RPS ja enviado nesta serie.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Servicos</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {Object.entries(cfg.servicos).map(([codigo, s]) => (
            <div key={codigo} className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="font-mono font-semibold">{codigo}</p>
                <Button variant="ghost" size="sm" className="text-red-600" onClick={() => removerServico(codigo)}>
                  Remover
                </Button>
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="space-y-1 sm:col-span-2">
                  <Label>Descricao padrao</Label>
                  <Input
                    value={s.descricao_padrao}
                    onChange={(e) => setServico(codigo, "descricao_padrao", e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label>Aliquota do ISS</Label>
                  <div className="relative">
                    <Input
                      className="pr-8 text-right tabular-nums"
                      inputMode="numeric"
                      value={fracaoParaPercentual(s.aliquota)}
                      onChange={(e) =>
                        setServico(codigo, "aliquota", percentualParaFracao(e.target.value))
                      }
                      placeholder="0,00"
                    />
                    <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                      %
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Em porcentagem: digite 200 para 2,00%. Vai como {s.aliquota} no XML
                  </p>
                </div>
                <div className="flex items-center gap-2 pt-5">
                  <Switch
                    checked={s.iss_retido}
                    onCheckedChange={(v) => setServico(codigo, "iss_retido", v)}
                  />
                  <Label>ISS retido</Label>
                </div>
                <div className="space-y-1">
                  <Label>NBS</Label>
                  <Input
                    className="tabular-nums"
                    inputMode="numeric"
                    value={s.nbs}
                    placeholder="000000000"
                    onChange={(e) => setServico(codigo, "nbs", mascaraCodigo(e.target.value, 9))}
                    onBlur={(e) => setServico(codigo, "nbs", completarCodigo(e.target.value, 9))}
                  />
                  <p className="text-xs text-muted-foreground">
                    9 digitos. Codigo curto ganha zeros a esquerda ao sair do campo
                  </p>
                </div>
                <div className="space-y-1">
                  <Label>cClassTrib</Label>
                  <Input
                    className="tabular-nums"
                    inputMode="numeric"
                    value={s.c_class_trib}
                    placeholder="000000"
                    onChange={(e) =>
                      setServico(codigo, "c_class_trib", mascaraCodigo(e.target.value, 6))
                    }
                    onBlur={(e) =>
                      setServico(codigo, "c_class_trib", completarCodigo(e.target.value, 6))
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    6 digitos, classificacao tributaria IBS/CBS (confirmar com o contador)
                  </p>
                </div>
                <div className="space-y-1">
                  <Label>cIndOp</Label>
                  <Input
                    className="tabular-nums"
                    inputMode="numeric"
                    value={s.c_ind_op}
                    placeholder="000000"
                    onChange={(e) =>
                      setServico(codigo, "c_ind_op", mascaraCodigo(e.target.value, 6))
                    }
                    onBlur={(e) =>
                      setServico(codigo, "c_ind_op", completarCodigo(e.target.value, 6))
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    6 digitos, indicador de operacao do Anexo VII
                  </p>
                </div>
                <div className="space-y-1">
                  <Label>Cod. municipio da prestacao</Label>
                  <Input
                    className="tabular-nums"
                    inputMode="numeric"
                    value={s.c_loc_prestacao ?? "3550308"}
                    onChange={(e) =>
                      setServico(codigo, "c_loc_prestacao", mascaraCodigo(e.target.value, 7))
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    IBGE, 7 digitos. Sao Paulo e 3550308
                  </p>
                </div>
                <div className="space-y-1">
                  <Label>Codigo de tributacao nacional</Label>
                  <Input
                    className="tabular-nums"
                    inputMode="numeric"
                    value={s.c_trib_nac ?? ""}
                    placeholder="080201"
                    onChange={(e) =>
                      setServico(codigo, "c_trib_nac", mascaraCodigo(e.target.value, 6))
                    }
                    onBlur={(e) =>
                      e.target.value &&
                      setServico(codigo, "c_trib_nac", completarCodigo(e.target.value, 6))
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Ambiente nacional, 6 digitos (Anexo I). Instrucao e treinamento e 080201
                  </p>
                </div>
                <div className="space-y-1">
                  <Label>NBS (nacional, opcional)</Label>
                  <Input
                    className="tabular-nums"
                    inputMode="numeric"
                    value={s.c_nbs ?? ""}
                    placeholder="000000000"
                    onChange={(e) => setServico(codigo, "c_nbs", mascaraCodigo(e.target.value, 9))}
                  />
                  <p className="text-xs text-muted-foreground">
                    9 digitos. Vazio fica de fora da DPS
                  </p>
                </div>
              </div>
              <Separator />
            </div>
          ))}

          <div className="flex items-end gap-2">
            <div className="space-y-1">
              <Label>Novo codigo de servico</Label>
              <Input
                className="tabular-nums"
                inputMode="numeric"
                value={novoCodigo}
                placeholder="05762"
                onChange={(e) => setNovoCodigo(mascaraCodigo(e.target.value, 5))}
              />
              <p className="text-xs text-muted-foreground">
                Codigo municipal de 4 ou 5 digitos (cursos 05762, consultoria 02881)
              </p>
            </div>
            <Button variant="outline" onClick={adicionarServico}>
              Adicionar
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Valores de cClassTrib e cIndOp devem ser confirmados com o contador antes de
            emitir nota real para cliente.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
