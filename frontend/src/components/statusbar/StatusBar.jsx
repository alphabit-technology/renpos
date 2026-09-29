export default function StatusBar() {
  return (
    <div className="rm-statusbar flex items-center justify-between px-4 py-2 text-sm">
      <div className="flex items-center gap-4">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-green-400"></span>
          Conectado
        </span>
      </div>
      
      <div className="flex items-center gap-4">
        <span>Usuario: {frappe.session?.user || 'Guest'}</span>
      </div>
    </div>
  )
}