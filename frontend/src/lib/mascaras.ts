/**
 * Mascaras de entrada. Regra geral: o usuario digita do jeito que quiser
 * (com ou sem pontuacao, ponto ou virgula) e a mascara normaliza. O que vai
 * pra API e sempre o formato canonico, nunca o texto formatado da tela.
 */

export function soDigitos(v: string): string {
  return (v ?? "").replace(/\D/g, "")
}

/** CPF 111.444.777-35 ou CNPJ 04.891.850/0001-88, conforme o tamanho. */
export function mascaraCpfCnpj(v: string): string {
  const d = soDigitos(v).slice(0, 14)
  if (d.length <= 11) {
    return d
      .replace(/^(\d{3})(\d)/, "$1.$2")
      .replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/\.(\d{3})(\d{1,2})$/, ".$1-$2")
  }
  return d
    .replace(/^(\d{2})(\d)/, "$1.$2")
    .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
    .replace(/\.(\d{3})(\d)/, ".$1/$2")
    .replace(/(\d{4})(\d{1,2})$/, "$1-$2")
}

export function ehCnpj(v: string): boolean {
  return soDigitos(v).length > 11
}

/** true quando o documento esta completo (11 ou 14 digitos) e com DV valido. */
export function documentoValido(v: string): boolean {
  const d = soDigitos(v)
  if (d.length === 11) return validarCpf(d)
  if (d.length === 14) return validarCnpj(d)
  return false
}

function validarCpf(cpf: string): boolean {
  if (/^(\d)\1{10}$/.test(cpf)) return false
  const dv = (ate: number) => {
    let soma = 0
    for (let i = 0; i < ate; i++) soma += Number(cpf[i]) * (ate + 1 - i)
    const resto = soma % 11
    return resto < 2 ? 0 : 11 - resto
  }
  return Number(cpf[9]) === dv(9) && Number(cpf[10]) === dv(10)
}

function validarCnpj(cnpj: string): boolean {
  if (/^(\d)\1{13}$/.test(cnpj)) return false
  const pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
  const pesos2 = [6, ...pesos1]
  const dv = (pesos: number[]) => {
    const soma = pesos.reduce((acc, p, i) => acc + Number(cnpj[i]) * p, 0)
    const resto = soma % 11
    return resto < 2 ? 0 : 11 - resto
  }
  return Number(cnpj[12]) === dv(pesos1) && Number(cnpj[13]) === dv(pesos2)
}

/** CEP 01310-100 */
export function mascaraCep(v: string): string {
  const d = soDigitos(v).slice(0, 8)
  return d.length > 5 ? `${d.slice(0, 5)}-${d.slice(5)}` : d
}

/**
 * Moeda em pt-BR: usuario digita so digitos e ve 1.234,56 se formando da
 * direita pra esquerda. Elimina a duvida de ponto vs virgula, porque nao
 * existe tecla de separador a acertar.
 */
export function mascaraMoeda(v: string): string {
  const d = soDigitos(v).slice(0, 13)
  if (!d) return ""
  const centavos = Number(d) / 100
  return centavos.toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

/** "1.234,56" -> 1234.56 (o numero que a API recebe). */
export function moedaParaNumero(v: string): number {
  const d = soDigitos(v)
  return d ? Number(d) / 100 : 0
}

/** 1234.56 -> "1.234,56" (para pre-preencher o campo). */
export function numeroParaMoeda(n: number): string {
  return mascaraMoeda(String(Math.round((n || 0) * 100)))
}

/**
 * Percentual com 2 casas: usuario digita digitos e ve 2,00. A API recebe a
 * fracao (0.02), que e o formato do XML.
 */
export function mascaraPercentual(v: string): string {
  const d = soDigitos(v).slice(0, 6)
  if (!d) return ""
  return (Number(d) / 100).toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

/** "2,00" -> 0.02 */
export function percentualParaFracao(v: string): number {
  const d = soDigitos(v)
  return d ? Number(d) / 10000 : 0
}

/** 0.02 -> "2,00" */
export function fracaoParaPercentual(n: number): string {
  return mascaraPercentual(String(Math.round((n || 0) * 10000)))
}

/** Codigo numerico de largura maxima fixa (servico, NBS, cClassTrib, cIndOp). */
export function mascaraCodigo(v: string, tamanho: number): string {
  return soDigitos(v).slice(0, tamanho)
}

/** Completa com zeros a esquerda, como o backend faz antes de montar o XML. */
export function completarCodigo(v: string, tamanho: number): string {
  const d = soDigitos(v)
  return d ? d.padStart(tamanho, "0") : ""
}
