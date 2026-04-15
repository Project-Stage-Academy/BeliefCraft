import React, { useState, useRef, useEffect } from 'react';

export type Option = {
  label: string;
  value: string;
  disabled?: boolean;
};

type CustomSelectProps = {
  options: Option[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  id?: string;
};

export function CustomSelect({
  options,
  value,
  onChange,
  placeholder = '—',
  disabled = false,
  id,
}: CustomSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const selectedOption = options.find((opt) => opt.value === value);
  const displayValue = selectedOption ? selectedOption.label : placeholder;

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (isOpen && highlightedIndex >= 0 && highlightedIndex < options.length) {
        onChange(options[highlightedIndex].value);
        setIsOpen(false);
      } else {
        setIsOpen((prev) => !prev);
      }
    } else if (e.key === 'Escape') {
      setIsOpen(false);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!isOpen) setIsOpen(true);
      setHighlightedIndex((prev) => (prev < options.length - 1 ? prev + 1 : prev));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (!isOpen) setIsOpen(true);
      setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : 0));
    }
  };

  useEffect(() => {
    if (isOpen) {
      const idx = options.findIndex((opt) => opt.value === value);
      setHighlightedIndex(idx >= 0 ? idx : 0);
    }
  }, [isOpen, value, options]);

  return (
    <div
      ref={wrapperRef}
      className={`custom-select-wrapper ${isOpen ? 'open' : ''} ${disabled ? 'disabled' : ''}`}
      id={id ? `${id}-wrapper` : undefined}
    >
      <div
        className={`custom-select ${isOpen ? 'active' : ''}`}
        tabIndex={disabled ? -1 : 0}
        onClick={() => !disabled && setIsOpen(!isOpen)}
        onKeyDown={handleKeyDown}
      >
        <span className="custom-select-value">{displayValue}</span>
        <svg
          className="custom-select-chevron"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      </div>

      <div className={`custom-options ${isOpen ? 'open' : ''}`}>
        {options.map((opt, idx) => (
          <div
            key={`${opt.value}-${idx}`}
            className={`custom-option ${opt.disabled ? 'placeholder' : ''} ${
              opt.value === value ? 'selected' : ''
            } ${idx === highlightedIndex ? 'highlighted' : ''}`}
            onClick={(e) => {
              e.stopPropagation();
              if (!opt.disabled) {
                onChange(opt.value);
                setIsOpen(false);
              }
            }}
          >
            {opt.label}
          </div>
        ))}
      </div>
    </div>
  );
}
