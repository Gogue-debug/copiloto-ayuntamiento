/**
 * Back-office: Revisión y firma de resoluciones generadas por IA.
 *
 * Flujo human-in-the-loop:
 *   AI_DRAFT → (staff revisa) → APPROVED → (firma digital) → SIGNED
 *
 * Solo accesible para roles: funcionario, secretario, alcalde
 */
import Link from "next/link";

export default function ResolucionesPage() {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">
            Resoluciones — Revisión de Borradores
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Revise los borradores generados por el asistente de IA
          </p>
        </div>
        <Link href="/" className="text-sm text-blue-600 hover:underline">
          ← Volver al inicio
        </Link>
      </header>

      <div className="max-w-5xl mx-auto px-6 py-8">
        {/* Alert legal */}
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-sm text-yellow-800 mb-6">
          <strong>Aviso legal:</strong> Los borradores generados por inteligencia
          artificial requieren revisión y validación por el funcionario o
          Secretario competente antes de su firma y efectos jurídicos (Ley
          39/2015, art. 41).
        </div>

        {/* Workflow status */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4">Flujo de estados</h2>
          <div className="flex items-center gap-3 text-sm">
            <span className="bg-blue-100 text-blue-700 px-3 py-1 rounded-full font-medium">
              AI_DRAFT
            </span>
            <span className="text-gray-400">→</span>
            <span className="bg-amber-100 text-amber-700 px-3 py-1 rounded-full font-medium">
              PENDING_REVIEW
            </span>
            <span className="text-gray-400">→</span>
            <span className="bg-green-100 text-green-700 px-3 py-1 rounded-full font-medium">
              APPROVED
            </span>
            <span className="text-gray-400">→</span>
            <span className="bg-purple-100 text-purple-700 px-3 py-1 rounded-full font-medium">
              SIGNED
            </span>
          </div>
        </div>

        {/* Empty state table */}
        <div className="bg-white rounded-xl border border-gray-200">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold">Borradores pendientes</h2>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="text-left px-6 py-3 font-medium text-gray-500">
                  Expediente
                </th>
                <th className="text-left px-6 py-3 font-medium text-gray-500">
                  Tipo
                </th>
                <th className="text-left px-6 py-3 font-medium text-gray-500">
                  Estado
                </th>
                <th className="text-left px-6 py-3 font-medium text-gray-500">
                  Fecha
                </th>
                <th className="text-left px-6 py-3 font-medium text-gray-500">
                  Acciones
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td
                  colSpan={5}
                  className="px-6 py-12 text-center text-gray-400"
                >
                  No hay borradores pendientes de revisión
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
