import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"
import { FileTextIcon } from "lucide-react"
import { LoginForm } from "@/components/login-form"
import { api, ApiError } from "@/lib/api"

export default function Login() {
  const navigate = useNavigate()
  const [usuario, setUsuario] = useState("")
  const [senha, setSenha] = useState("")
  const [carregando, setCarregando] = useState(false)

  async function entrar(evento: React.FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    setCarregando(true)
    try {
      await api.login(usuario, senha)
      navigate("/notas")
    } catch (erro) {
      const mensagem =
        erro instanceof ApiError && erro.status === 429
          ? "Muitas tentativas. Aguarde um minuto."
          : "Usuario ou senha incorretos"
      toast.error(mensagem)
    } finally {
      setCarregando(false)
    }
  }

  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-6 bg-muted p-6 md:p-10">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <div className="flex items-center justify-center gap-2 font-semibold">
          <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <FileTextIcon className="size-4" />
          </span>
          NFS-e Sao Paulo
        </div>
        <LoginForm
          usuario={usuario}
          senha={senha}
          carregando={carregando}
          onUsuarioChange={setUsuario}
          onSenhaChange={setSenha}
          onSubmit={entrar}
        />
      </div>
    </main>
  )
}
