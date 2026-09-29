import {Button} from "./Button.tsx"
import { useState, useRef, useCallback } from 'react'

const CONFIRM_TIMEOUT = 5000;

export function ActionButton({ 
  icon: Icon, 
  label, 
  confirmLabel,
  onClick, 
  variant = 'primary', 
  confirmVariant = 'destructive',
  confirm = false,
  className = ''
}) {
  const [waiting, setWaiting] = useState(false);
  const timerRef = useRef(null);

  const reset = useCallback(() => {
    clearTimeout(timerRef.current);
    timerRef.current = null;
    setWaiting(false);
  }, []);

  const handleClick = useCallback((e) => {
    if (!confirm) {
      onClick?.(e);
      return;
    }

    if (waiting) {
      reset();
      onClick?.();
    } else {
      setWaiting(true);
      timerRef.current = setTimeout(reset, CONFIRM_TIMEOUT);
    }
  }, [confirm, waiting, onClick, reset]);

  return (
    <Button
      variant={waiting ? confirmVariant : variant}
      className={`${className} ${waiting ? 'animate-pulse' : ''}`}
      onClick={handleClick}
    >
      {Icon && <Icon size={16} />}
      {label && <span>{waiting ? (confirmLabel || label) : label}</span>}
    </Button>
  )
}
