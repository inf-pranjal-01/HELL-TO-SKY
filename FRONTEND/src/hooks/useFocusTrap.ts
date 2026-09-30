import { useEffect, useRef } from "react";
const FOCUSABLE_SELECTORS = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(", ");
export interface UseFocusTrapOptions {
  initialFocusRef?: React.RefObject<HTMLElement>;
  triggerRef?: React.RefObject<HTMLElement>;
}
export function useFocusTrap<T extends HTMLElement>(
  isActive: boolean,
  onClose: () => void,
  options?: UseFocusTrapOptions,
) {
  const containerRef = useRef<T>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);
  useEffect(() => {
    if (!isActive) return;
    previousFocusRef.current = document.activeElement as HTMLElement;
    const focusTimer = setTimeout(() => {
      if (!containerRef.current) return;
      if (options?.initialFocusRef?.current) {
        options.initialFocusRef.current.focus();
        return;
      }
      const focusable =
        containerRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTORS);
      if (focusable.length) focusable[0].focus();
    }, 50);
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab" || !containerRef.current) return;
      const focusable = Array.from(
        containerRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTORS),
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      clearTimeout(focusTimer);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isActive, options?.initialFocusRef]);
  useEffect(() => {
    if (!isActive) {
      if (options?.triggerRef?.current) {
        options.triggerRef.current.focus();
        previousFocusRef.current = null;
      } else if (previousFocusRef.current) {
        previousFocusRef.current.focus();
        previousFocusRef.current = null;
      }
    }
  }, [isActive, options?.triggerRef]);
  return containerRef;
}
let liveRegionEl: HTMLElement | null = null;
export function announceToScreenReader(message: string, politeness: "polite" | "assertive" = "assertive"): void {
  if (typeof document === "undefined") return;
  if (!liveRegionEl) {
    liveRegionEl = document.createElement("div");
    liveRegionEl.setAttribute("role", "status");
    liveRegionEl.setAttribute("aria-live", "assertive");
    liveRegionEl.setAttribute("aria-atomic", "true");
    Object.assign(liveRegionEl.style, {
      position: "absolute",
      width: "1px",
      height: "1px",
      padding: "0",
      margin: "-1px",
      overflow: "hidden",
      clip: "rect(0, 0, 0, 0)",
      whiteSpace: "nowrap",
      border: "0",
    });
    document.body.appendChild(liveRegionEl);
  }
  liveRegionEl.setAttribute("aria-live", politeness);
  liveRegionEl.textContent = "";
  requestAnimationFrame(() => {
    if (liveRegionEl) liveRegionEl.textContent = message;
  });
}
