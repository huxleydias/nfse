import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"

type LoginFormProps = Omit<React.ComponentProps<"div">, "onSubmit"> & {
  usuario: string
  senha: string
  carregando: boolean
  onUsuarioChange: (valor: string) => void
  onSenhaChange: (valor: string) => void
  onSubmit: (evento: React.FormEvent<HTMLFormElement>) => void
}

export function LoginForm({
  className,
  usuario,
  senha,
  carregando,
  onUsuarioChange,
  onSenhaChange,
  onSubmit,
  ...props
}: LoginFormProps) {
  return (
    <div className={cn("flex flex-col gap-6", className)} {...props}>
      <Card>
        <CardHeader className="text-center">
          <CardTitle className="text-xl">Acesse sua conta</CardTitle>
          <CardDescription>
            Entre com seu usuario e senha para gerenciar suas notas fiscais
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit}>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="usuario">Usuario</FieldLabel>
                <Input
                  id="usuario"
                  value={usuario}
                  onChange={(evento) => onUsuarioChange(evento.target.value)}
                  autoComplete="username"
                  autoFocus
                  required
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="senha">Senha</FieldLabel>
                <Input
                  id="senha"
                  type="password"
                  value={senha}
                  onChange={(evento) => onSenhaChange(evento.target.value)}
                  autoComplete="current-password"
                  required
                />
              </Field>
              <Field>
                <Button type="submit" disabled={carregando}>
                  {carregando ? "Entrando..." : "Entrar"}
                </Button>
              </Field>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
