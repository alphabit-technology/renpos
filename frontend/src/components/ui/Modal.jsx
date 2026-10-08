import { useEffect, useCallback, useRef } from 'react'
import { createPortal } from 'react-dom'
import { X, MoveLeft, CornerLeftUp } from 'lucide-react'

function Modal({
  open,
  onClose,
  title,
  children,
  size = 'lg', // 'sm' | 'md' | 'lg' | 'xl' | 'full'
  closeOnEsc = true,
  closeOnOverlay = true,
  showClose = true,
  headerActions,
  footer,
  className = '',
  compactHeader = false,
  hasReturn = false
}) {
  const modalRef = useRef(null);

  const fullscreen = size === "full"

  // ESC to close
  useEffect(() => {
    if (!open || !closeOnEsc) return;
    const handler = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, closeOnEsc, onClose]);

  // Lock body scroll
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, [open]);

  // Focus trap
  useEffect(() => {
    if (!open || !modalRef.current) return;
    const prev = document.activeElement;
    modalRef.current.focus();
    return () => prev?.focus?.();
  }, [open]);

  const handleOverlayClick = useCallback((e) => {
    if (closeOnOverlay && e.target === e.currentTarget) {
      onClose?.();
    }
  }, [closeOnOverlay, onClose]);

  if (!open) return null;

  const sizeClasses = fullscreen
    ? 'w-full h-full'
    : {
        sm: 'w-full max-w-md max-h-[70vh]',
        md: 'w-full max-w-2xl max-h-[80vh]',
        lg: 'w-full max-w-4xl max-h-[85vh]',
        xl: 'w-full max-w-6xl max-h-[90vh]',
        full: 'w-full h-full',
      }[size] || 'w-full max-w-4xl max-h-[85vh]';

  const roundedClass = fullscreen ? '' : 'rounded-2xl m-4';

  return createPortal(
    <div
      className={`ren-portal fixed inset-0 z-[1020] flex items-center justify-center bg-black/70 backdrop-blur-sm animate-fade-in`}
      onClick={handleOverlayClick}
    >
      <div
        ref={modalRef}
        tabIndex={-1}
        className={`
          ${sizeClasses} ${roundedClass}
          bg-[var(--card-bg,#1a1a2e)] flex flex-col overflow-hidden
          outline-none shadow-2xl shadow-black/40
          ${className}
        `}
      >
        {/* Header */}
        {(title || showClose || headerActions) && (
          <div className={
            `flex items-center justify-between ${compactHeader ? 'p-1' : 'py-3 px-3'} border-b border-white/10 shrink-0`
          }>
          <div className="flex flex-row items-center gap-2 min-w-0 flex-1">
            {hasReturn ? (
              <button className="p-1 rounded-lg ... shrink-0" onClick={onClose}>
                <MoveLeft size={20} />
              </button>
            ) : null}
            <h2 className="text-lg font-semibold ... m-0 min-w-0 flex-1 overflow-hidden">
              {title}
            </h2>
          </div>
          
          <div className="flex items-center gap-2 shrink-0">
            {headerActions}
            {showClose && (
              <button
                className="p-1.5 rounded-lg text-[var(--text-muted,#888)] hover:text-white hover:bg-white/10 transition-all"
                onClick={onClose}
                aria-label="Close"
              >
                <X size={20} />
              </button>
            )}
          </div>
        </div>
        )}

        {/* Body */}
        <div className="flex-1 overflow-y-auto">
          {children}
        </div>

        {/* Footer */}
        {footer && (
          <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-white/10 shrink-0">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}

export default Modal;