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
import { CampoCodigo, CampoPercentual } from "@/components/campos"
import {
  documentoValido,
  fracaoParaPorcentagem,
  mascaraCodigo,
  mascaraCpfCnpj,
  numeroParaTexto,
  porcentagemParaFracao,
  soDigitos,
} from "@/lib/mascaras"

// Nenhuma aliquota nominal do Simples fica abaixo de 4%: valor menor e quase
// sempre fracao digitada no lugar de porcentagem
function avisoSimples(n: number) {
  if (n > 0 && n < 4) {
    return `A aliquota do Simples comeca em 4%. Para 11,2% digite 11,2 (hoje esta ${numeroParaTexto(n)}%).`
  }
  return null
}

function avisoIss(n: number) {
  if (n > 0 && n < 1) return "Digite em porcentagem: 2 para 2%."
  if (n > 5) return "O ISS municipal vai ate 5%."
  return null
}

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
  c_loc_prestacao: "",
  c_trib_nac: "",
  c_trib_mun: "",
  c_nbs: "",
}

export default function Config() {
  const [cfg, setCfg] = useState<ConfigT | null>(null)
  const [salvando, setSalvando] = useState(false)
  const [novoCodigo, setNovoCodigo] = useState("")

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
    setCfg(
      (c) =>
        c && {
          ...c,
          servicos: {
            ...c.servicos,
            [codigo]: { ...SERVICO_VAZIO, c_loc_prestacao: c.nacional.c_loc_emi },
          },
        },
    )
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
              <Label>Percentual do Simples</Label>
              <CampoPercentual
                valor={cfg.nacional.p_tot_trib_sn}
                aoMudar={(n) => setNacional("p_tot_trib_sn", n)}
                placeholder="11,2"
                aviso={avisoSimples}
              />
              <p className="text-xs text-muted-foreground">
                A aliquota da sua faixa do Simples, como o contador informa (ex.: 11,2). Vale para
                os servicos sem percentual proprio.
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
            <div className="space-y-2">
              <Label>Inscricao municipal no Sistema Nacional</Label>
              <Input
                className="tabular-nums"
                placeholder={cfg.prestador.inscricao_municipal}
                maxLength={15}
                value={cfg.nacional.inscricao_municipal ?? ""}
                onChange={(e) => setNacional("inscricao_municipal", e.target.value.replace(/\s/g, ""))}
              />
              <p className="text-xs text-muted-foreground">
                Copie o Indicador Municipal do prestador de uma nota emitida no Emissor Nacional.
                Em Sao Paulo e o CCM com zeros a esquerda ate 15 digitos. Vazio usa a inscricao do
                prestador.
              </p>
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

      {!nacional && (
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
          {cfg.layout === 2 && (
            <p className="text-xs text-muted-foreground">
              No layout 2 cada servico ganha os campos da reforma (NBS, cClassTrib, cIndOp).
            </p>
          )}
        </CardContent>
      </Card>
      )}

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

      {!nacional && (
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
      )}

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
                {!nacional && (
                  <>
                    <div className="space-y-1">
                      <Label>Aliquota do ISS</Label>
                      <CampoPercentual
                        valor={fracaoParaPorcentagem(s.aliquota)}
                        aoMudar={(n) => setServico(codigo, "aliquota", porcentagemParaFracao(n))}
                        placeholder="2"
                        aviso={avisoIss}
                      />
                      <p className="text-xs text-muted-foreground">Como na nota: 2 para 2%</p>
                    </div>
                    <div className="flex items-center gap-2 pt-5">
                      <Switch
                        checked={s.iss_retido}
                        onCheckedChange={(v) => setServico(codigo, "iss_retido", v)}
                      />
                      <Label>ISS retido pelo tomador</Label>
                    </div>
                  </>
                )}
                {nacional && (
                  <>
                    <div className="space-y-1">
                      <Label>Codigo de tributacao nacional</Label>
                      <CampoCodigo
                        valor={s.c_trib_nac}
                        aoMudar={(d) => setServico(codigo, "c_trib_nac", d)}
                        padrao="##.##.##"
                        placeholder="08.02.01"
                      />
                      <p className="text-xs text-muted-foreground">
                        Como aparece no DANFSe. Cursos: 08.02.01
                      </p>
                    </div>
                    <div className="space-y-1">
                      <Label>Codigo municipal (opcional)</Label>
                      <CampoCodigo
                        valor={s.c_trib_mun}
                        aoMudar={(d) => setServico(codigo, "c_trib_mun", d)}
                        padrao="###"
                        placeholder="001"
                        completarAte={3}
                      />
                      <p className="text-xs text-muted-foreground">
                        Os 3 digitos depois da barra no DANFSe (01.06.01 / 001)
                      </p>
                    </div>
                    <div className="space-y-1">
                      <Label>NBS (opcional)</Label>
                      <CampoCodigo
                        valor={s.c_nbs}
                        aoMudar={(d) => setServico(codigo, "c_nbs", d)}
                        padrao="#.####.##.##"
                        placeholder="1.2205.19.00"
                      />
                      <p className="text-xs text-muted-foreground">Como aparece no DANFSe</p>
                    </div>
                    <div className="space-y-1">
                      <Label>Percentual do Simples deste servico (opcional)</Label>
                      <CampoPercentual
                        valor={s.p_tot_trib_sn}
                        aoMudar={(n) => setServico(codigo, "p_tot_trib_sn", n)}
                        placeholder={numeroParaTexto(cfg.nacional.p_tot_trib_sn) || "11,2"}
                        aviso={avisoSimples}
                      />
                      <p className="text-xs text-muted-foreground">
                        Vazio usa o percentual geral
                        {cfg.nacional.p_tot_trib_sn != null &&
                          ` (${numeroParaTexto(cfg.nacional.p_tot_trib_sn)}%)`}
                      </p>
                    </div>
                  </>
                )}
                {(nacional || cfg.layout === 2) && (
                  <div className="space-y-1">
                    <Label>Municipio da prestacao (IBGE)</Label>
                    <Input
                      className="tabular-nums"
                      inputMode="numeric"
                      value={s.c_loc_prestacao ?? ""}
                      placeholder={cfg.nacional.c_loc_emi}
                      onChange={(e) =>
                        setServico(codigo, "c_loc_prestacao", mascaraCodigo(e.target.value, 7))
                      }
                    />
                    <p className="text-xs text-muted-foreground">7 digitos. Sao Paulo e 3550308</p>
                  </div>
                )}
                {!nacional && cfg.layout === 2 && (
                  <>
                    <div className="space-y-1">
                      <Label>NBS</Label>
                      <CampoCodigo
                        valor={s.nbs}
                        aoMudar={(d) => setServico(codigo, "nbs", d)}
                        padrao="#.####.##.##"
                        placeholder="1.2205.19.00"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label>Classificacao tributaria IBS/CBS (cClassTrib)</Label>
                      <CampoCodigo
                        valor={s.c_class_trib}
                        aoMudar={(d) => setServico(codigo, "c_class_trib", d)}
                        padrao="######"
                        placeholder="000001"
                        completarAte={6}
                      />
                      <p className="text-xs text-muted-foreground">Confirme com o contador</p>
                    </div>
                    <div className="space-y-1">
                      <Label>Indicador da operacao (cIndOp)</Label>
                      <CampoCodigo
                        valor={s.c_ind_op}
                        aoMudar={(d) => setServico(codigo, "c_ind_op", d)}
                        padrao="######"
                        placeholder="030101"
                        completarAte={6}
                      />
                      <p className="text-xs text-muted-foreground">Anexo VII da reforma</p>
                    </div>
                  </>
                )}
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
        </CardContent>
      </Card>
    </div>
  )
}
