/**
 * Portal ciudadano — Página principal con widget de chat.
 * Accesible sin autenticación (ciudadanos anónimos).
 */
import Link from "next/link";

export default function CiudadanoPage() {
  return (
    <main className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">
            Ayuntamiento — Asistente Virtual
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Le atendemos 24 horas al día, 7 días a la semana
          </p>
        </div>
        <Link href="/" className="text-sm text-blue-600 hover:underline">
          ← Volver al inicio
        </Link>
      </header>

      <div className="max-w-3xl mx-auto px-4 py-8">
        {/* ChatWidget se cargará aquí como Client Component */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 h-[600px] flex flex-col">
          <div className="border-b border-gray-200 px-4 py-3">
            <div className="flex items-center gap-2">
              <div className="w-2.5 h-2.5 bg-green-500 rounded-full" />
              <span className="text-sm font-medium text-gray-700">
                Asistente disponible
              </span>
            </div>
          </div>
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <p className="text-gray-400 text-sm mb-2">
                Escriba su consulta para comenzar
              </p>
              <p className="text-xs text-gray-300">
                ChatWidget — próximamente
              </p>
            </div>
          </div>
          <div className="border-t border-gray-200 px-4 py-3">
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="Escriba su consulta aquí..."
                className="flex-1 border border-gray-300 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                disabled
              />
              <button
                className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium opacity-50 cursor-not-allowed"
                disabled
              >
                Enviar
              </button>
            </div>
          </div>
        </div>

        <p className="text-xs text-gray-400 text-center mt-4">
          Este asistente le proporciona información orientativa. Para actos
          administrativos con efectos jurídicos, contacte con el Ayuntamiento.
          Sus datos se tratan conforme al RGPD — consulte nuestra política de
          privacidad.
        </p>
      </div>
    </main>
  );
}
