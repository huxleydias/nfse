import { describe, expect, it } from "vitest"

import {
  completarCodigo,
  documentoValido,
  ehCnpj,
  formatarCodigo,
  fracaoParaPorcentagem,
  limparDecimal,
  mascaraCep,
  mascaraCodigo,
  mascaraCpfCnpj,
  mascaraMoeda,
  moedaParaNumero,
  numeroParaMoeda,
  numeroParaTexto,
  porcentagemParaFracao,
  soDigitos,
  textoParaNumero,
} from "./mascaras"

describe("mascaraCpfCnpj", () => {
  it("formata cpf parcial enquanto digita", () => {
    expect(mascaraCpfCnpj("111")).toBe("111")
    expect(mascaraCpfCnpj("111444")).toBe("111.444")
    expect(mascaraCpfCnpj("11144477735")).toBe("111.444.777-35")
  })

  it("formata cnpj quando passa de 11 digitos", () => {
    expect(mascaraCpfCnpj("04891850000188")).toBe("04.891.850/0001-88")
  })

  it("e idempotente sobre texto ja formatado", () => {
    expect(mascaraCpfCnpj("111.444.777-35")).toBe("111.444.777-35")
    expect(mascaraCpfCnpj("04.891.850/0001-88")).toBe("04.891.850/0001-88")
  })

  it("descarta letras e limita a 14 digitos", () => {
    expect(soDigitos(mascaraCpfCnpj("04891850000188999abc"))).toHaveLength(14)
  })
})

describe("ehCnpj", () => {
  it("distingue por quantidade de digitos", () => {
    expect(ehCnpj("111.444.777-35")).toBe(false)
    expect(ehCnpj("04.891.850/0001-88")).toBe(true)
  })
})

describe("documentoValido", () => {
  it("aceita cpf e cnpj com digito verificador correto", () => {
    expect(documentoValido("111.444.777-35")).toBe(true)
    expect(documentoValido("11.222.333/0001-81")).toBe(true)
  })

  it("recusa digito verificador errado", () => {
    expect(documentoValido("111.444.777-99")).toBe(false)
    expect(documentoValido("11.222.333/0001-82")).toBe(false)
  })

  it("recusa sequencia repetida e documento incompleto", () => {
    expect(documentoValido("111.111.111-11")).toBe(false)
    expect(documentoValido("1114447")).toBe(false)
  })
})

describe("mascaraCep", () => {
  it("insere o hifen", () => {
    expect(mascaraCep("01310100")).toBe("01310-100")
    expect(mascaraCep("013")).toBe("013")
  })
})

describe("moeda", () => {
  it("monta o valor da direita para a esquerda", () => {
    expect(mascaraMoeda("1")).toBe("0,01")
    expect(mascaraMoeda("59900")).toBe("599,00")
    expect(mascaraMoeda("123456789")).toBe("1.234.567,89")
  })

  it("converte para o numero que vai na API", () => {
    expect(moedaParaNumero("1.234,56")).toBe(1234.56)
    expect(moedaParaNumero("599,00")).toBe(599)
    expect(moedaParaNumero("")).toBe(0)
  })

  it("faz o caminho de volta para preencher o campo", () => {
    expect(numeroParaMoeda(599)).toBe("599,00")
    expect(numeroParaMoeda(1234.56)).toBe("1.234,56")
  })
})

describe("porcentagem", () => {
  it("le o numero do jeito que se escreve na nota", () => {
    expect(textoParaNumero("2")).toBe(2)
    expect(textoParaNumero("2,9")).toBe(2.9)
    expect(textoParaNumero("11.2")).toBe(11.2)
    expect(textoParaNumero("11,2%")).toBe(11.2)
    expect(textoParaNumero("")).toBeNull()
  })

  it("mantem so digitos e uma virgula enquanto digita", () => {
    expect(limparDecimal("11,")).toBe("11,")
    expect(limparDecimal("1,1,2")).toBe("1,12")
    expect(limparDecimal("abc2.9")).toBe("2,9")
  })

  it("exibe sem zeros sobrando", () => {
    expect(numeroParaTexto(11.2)).toBe("11,2")
    expect(numeroParaTexto(2)).toBe("2")
    expect(numeroParaTexto(null)).toBe("")
  })

  it("converte a aliquota do ISS entre porcentagem e a fracao guardada", () => {
    expect(fracaoParaPorcentagem(0.029)).toBe(2.9)
    expect(fracaoParaPorcentagem(0.02)).toBe(2)
    expect(porcentagemParaFracao(2.9)).toBe(0.029)
    expect(porcentagemParaFracao(5)).toBe(0.05)
    expect(porcentagemParaFracao(null)).toBe(0)
  })
})

describe("codigos fiscais", () => {
  it("aceita so digitos e trunca no tamanho", () => {
    expect(mascaraCodigo("05762abc9", 5)).toBe("05762")
    expect(mascaraCodigo("1.2001.10", 9)).toBe("1200110")
  })

  it("completa com zeros a esquerda, igual ao backend", () => {
    expect(completarCodigo("1", 6)).toBe("000001")
    expect(completarCodigo("620001", 6)).toBe("620001")
    expect(completarCodigo("1", 9)).toBe("000000001")
  })

  it("nao inventa codigo quando o campo esta vazio", () => {
    expect(completarCodigo("", 6)).toBe("")
  })

  it("formata como no DANFSe enquanto digita", () => {
    expect(formatarCodigo("080201", "##.##.##")).toBe("08.02.01")
    expect(formatarCodigo("0802", "##.##.##")).toBe("08.02")
    expect(formatarCodigo("122051900", "#.####.##.##")).toBe("1.2205.19.00")
    expect(formatarCodigo("", "##.##.##")).toBe("")
  })
})
