import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { Toaster } from "@/components/ui/sonner"
import Layout from "@/pages/Layout"
import Login from "@/pages/Login"
import Notas from "@/pages/Notas"
import Emitir from "@/pages/Emitir"
import Config from "@/pages/Config"
import Certificado from "@/pages/Certificado"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<Layout />}>
          <Route path="/" element={<Navigate to="/notas" replace />} />
          <Route path="/notas" element={<Notas />} />
          <Route path="/emitir" element={<Emitir />} />
          <Route path="/config" element={<Config />} />
          <Route path="/certificado" element={<Certificado />} />
        </Route>
      </Routes>
      <Toaster />
    </BrowserRouter>
  )
}
