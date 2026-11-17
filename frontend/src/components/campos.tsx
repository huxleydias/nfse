import { useState } from "react"
import { Input } from "@/components/ui/input"
import {
  formatarCodigo,
  limparDecimal,
  numeroParaTexto,
  soDigitos,
  textoParaNumero,
} from "@/lib/mascaras"

/**
 * Porcentagem digitada do jeito da nota: 2 para 2%, 11,2 para 11,2%. Quem
 * guarda em outra unidade (o ISS e fracao) converte fora daqui.
 */
export function CampoPercentual({
  valor,
  aoMudar,
  placeholder,
  aviso,
}: {
  valor: number | null | undefined
  aoMudar: (n: number | null) => void
  placeholder?: string
  /** Mensagem quando o numero parece errado (ex.: fracao no lugar de %) */
  aviso?: (n: number) => string | null
}) {
  // Texto enquanto digita: o numero sozinho perderia a virgula de "11,"
  const [texto, setTexto] = useState<string | null>(null)
  const mensagem = valor != null && aviso ? aviso(valor) : null
  return (
    <div className="space-y-1">
      <div className="relative">
        <Input
          className="pr-8 text-right tabular-nums"
          inputMode="decimal"
          value={texto ?? numeroParaTexto(valor)}
          placeholder={placeholder}
          aria-invalid={mensagem ? true : undefined}
          onChange={(e) => {
            const limpo = limparDecimal(e.target.value)
            setTexto(limpo)
            aoMudar(textoParaNumero(limpo))
          }}
          onBlur={() => setTexto(null)}
        />
        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
          %
        </span>
      </div>
      {mensagem && <p className="text-xs text-amber-700 dark:text-amber-400">{mensagem}</p>}
    </div>
  )
}

/**
 * Codigo fiscal exibido como no DANFSe (08.02.01, 1.2205.19.00) e guardado
 * so com digitos. Aceita colar com ou sem pontuacao.
 */
export function CampoCodigo({
  valor,
  aoMudar,
  padrao,
  placeholder,
  completarAte,
}: {
  valor: string | null | undefined
  aoMudar: (digitos: string) => void
  /** "#" e digito; o resto e pontuacao fixa. "###" para 3 digitos simples */
  padrao: string
  placeholder?: string
  /** Completa com zeros a esquerda ao sair do campo (ex.: 1 vira 001) */
  completarAte?: number
}) {
  const tamanho = (padrao.match(/#/g) ?? []).length
  return (
    <Input
      className="tabular-nums"
      inputMode="numeric"
      value={formatarCodigo(valor ?? "", padrao)}
      placeholder={placeholder}
      onChange={(e) => aoMudar(soDigitos(e.target.value).slice(0, tamanho))}
      onBlur={(e) => {
        const d = soDigitos(e.target.value)
        if (completarAte && d && d.length < completarAte) aoMudar(d.padStart(completarAte, "0"))
      }}
    />
  )
}
