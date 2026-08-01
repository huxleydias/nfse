export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail))
    this.status = status
    this.detail = detail
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers:
      options.body && !(options.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : undefined,
    ...options,
  })
  if (res.status === 401 && !path.includes("/auth/")) {
    window.location.href = "/login"
    throw new ApiError(401, "Sessao expirada")
  }
  const corpo = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new ApiError(res.status, (corpo as { detail?: unknown }).detail ?? corpo)
  }
  return corpo as T
}

export interface Nota {
  id: number
  ref_externa: string | null
  numero_rps: number | null
  serie_rps: string | null
  numero_nfse: string | null
  codigo_verificacao: string | null
  tomador_nome: string | null
  tomador_doc: string | null
  valor: number
  codigo_servico: string | null
  status: string
  erros_json: string | null
  criada_em: string
  atualizada_em: string
  xml_enviado?: string
  xml_retorno?: string
}

export interface ServicoConfig {
  descricao_padrao: string
  aliquota: number
  iss_retido: boolean
  nbs: string
  c_class_trib: string
  c_ind_op: string
  fin_nfse: number
  ind_final: number
  ind_dest: number
  c_loc_prestacao?: string
}

export interface Config {
  prestador: {
    cnpj: string
    inscricao_municipal: string
    razao_social: string
    email: string
  }
  servicos: Record<string, ServicoConfig>
  serie_rps: string
  proximo_numero_rps: number
  modo_teste: boolean
  tributacao: string
  layout: number
}

export interface CertificadoMeta {
  cn: string
  emissor: string
  valido_ate: string
  dias_restantes: number
  vencido: boolean
}

export const api = {
  login: (usuario: string, senha: string) =>
    request<{ ok: boolean }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ usuario, senha }),
    }),
  logout: () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),

  listarNotas: (filtros: { inicio?: string; fim?: string; status?: string }) => {
    const params = new URLSearchParams()
    if (filtros.inicio) params.set("inicio", filtros.inicio)
    if (filtros.fim) params.set("fim", filtros.fim)
    if (filtros.status) params.set("status", filtros.status)
    const qs = params.toString()
    return request<{ notas: Nota[] }>(`/api/notas${qs ? `?${qs}` : ""}`)
  },
  detalheNota: (id: number) => request<{ nota: Nota }>(`/api/notas/${id}`),
  emitirNota: (payload: unknown) =>
    request<{ teste: boolean; nota?: Nota; resultado?: unknown }>("/api/notas", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  /** PDF oficial da prefeitura. inline para visualizar, download para baixar. */
  urlPdf: (id: number, download = false) =>
    `/api/notas/${id}/pdf${download ? "?download=true" : ""}`,
  cancelarNota: (id: number) =>
    request<{ nota: Nota }>(`/api/notas/${id}`, { method: "DELETE" }),
  sincronizar: (inicio: string, fim: string) =>
    request<{ novas: number; atualizadas: number; total_remoto: number }>(
      "/api/notas/sync",
      { method: "POST", body: JSON.stringify({ inicio, fim }) },
    ),

  obterConfig: () => request<Config>("/api/config"),
  salvarConfig: (cfg: Partial<Config>) =>
    request<Config>("/api/config", { method: "PUT", body: JSON.stringify(cfg) }),

  statusCertificado: () =>
    request<{ certificado: CertificadoMeta | null }>("/api/certificado"),
  enviarCertificado: (arquivo: File, senha: string) => {
    const form = new FormData()
    form.append("arquivo", arquivo)
    form.append("senha", senha)
    return request<{ certificado: CertificadoMeta }>("/api/certificado", {
      method: "POST",
      body: form,
    })
  },
}
