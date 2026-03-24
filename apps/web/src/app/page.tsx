import Link from "next/link";

export default function HomePage() {
  return (
    <main className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-blue-800 text-white">
        <div className="max-w-6xl mx-auto px-6 py-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 bg-white/20 rounded-lg flex items-center justify-center text-xl">
              🏛
            </div>
            <h1 className="text-3xl font-bold">Copiloto Administrativo</h1>
          </div>
          <p className="text-blue-200 text-lg">
            Plataforma de asistencia inteligente para su Ayuntamiento
          </p>
        </div>
      </header>

      {/* Main content */}
      <div className="flex-1 max-w-6xl mx-auto px-6 py-12 w-full">
        <div className="grid md:grid-cols-2 gap-8">
          {/* Portal Ciudadano */}
          <Link
            href="/citizen"
            className="group block bg-white rounded-2xl shadow-sm border border-gray-200 p-8 hover:shadow-md hover:border-blue-300 transition-all"
          >
            <div className="w-14 h-14 bg-blue-100 rounded-xl flex items-center justify-center text-2xl mb-5 group-hover:bg-blue-200 transition-colors">
              💬
            </div>
            <h2 className="text-xl font-semibold mb-2">Portal Ciudadano</h2>
            <p className="text-gray-500 text-sm leading-relaxed">
              Consulte información sobre trámites, licencias de obra menor, vados
              permanentes, padrón municipal y más. Nuestro asistente virtual le
              atiende las 24 horas del día.
            </p>
            <span className="inline-block mt-4 text-blue-600 text-sm font-medium group-hover:underline">
              Acceder al asistente →
            </span>
          </Link>

          {/* Back-office */}
          <Link
            href="/backoffice/resoluciones"
            className="group block bg-white rounded-2xl shadow-sm border border-gray-200 p-8 hover:shadow-md hover:border-emerald-300 transition-all"
          >
            <div className="w-14 h-14 bg-emerald-100 rounded-xl flex items-center justify-center text-2xl mb-5 group-hover:bg-emerald-200 transition-colors">
              📋
            </div>
            <h2 className="text-xl font-semibold mb-2">Back-office Municipal</h2>
            <p className="text-gray-500 text-sm leading-relaxed">
              Gestión de resoluciones, revisión de borradores generados por IA,
              procesamiento de facturas por OCR y herramientas administrativas
              para el personal del Ayuntamiento.
            </p>
            <span className="inline-block mt-4 text-emerald-600 text-sm font-medium group-hover:underline">
              Acceder al panel →
            </span>
          </Link>
        </div>

        {/* Status cards */}
        <div className="grid md:grid-cols-3 gap-6 mt-12">
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="text-sm text-gray-500 mb-1">Estado del sistema</div>
            <div className="flex items-center gap-2">
              <div className="w-2.5 h-2.5 bg-green-500 rounded-full" />
              <span className="font-medium text-green-700">Operativo</span>
            </div>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="text-sm text-gray-500 mb-1">Modelo IA</div>
            <div className="font-medium">Claude Sonnet 4.6</div>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="text-sm text-gray-500 mb-1">Cumplimiento</div>
            <div className="font-medium">RGPD · ENS · Ley 39/2015</div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="bg-gray-100 border-t border-gray-200 py-6">
        <div className="max-w-6xl mx-auto px-6 text-center text-sm text-gray-500">
          <p>
            Copiloto Administrativo — Asistente con inteligencia artificial para
            Ayuntamientos
          </p>
          <p className="mt-1">
            La IA proporciona información orientativa. Las decisiones
            administrativas requieren validación humana conforme a la Ley
            39/2015.
          </p>
        </div>
      </footer>
    </main>
  );
}
