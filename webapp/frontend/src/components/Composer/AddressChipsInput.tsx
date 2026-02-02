// src/components/Composer/AddressChipsInput.tsx
import { useRef, useState } from "react";

type Props = {
  fieldId: string; // used for id attribute (composer-to, etc.)
  placeholder?: string;
  value: string[]; // chips
  onChange: (next: string[]) => void;
  className?: string;
};

function splitAddresses(raw: string): string[] {
  return raw
    .split(/[;,]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function AddressChipsInput({
  fieldId,
  placeholder,
  value,
  onChange,
  className,
}: Props) {
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  function commit() {
    const parts = splitAddresses(draft);
    if (!parts.length) return;
    onChange([...value, ...parts]);
    setDraft("");
  }

  function removeAt(idx: number) {
    const next = value.slice();
    next.splice(idx, 1);
    onChange(next);
  }

  return (
    <div className="composer-address-wrapper" data-field={fieldId.replace("composer-", "")}>
      <div className="composer-address-pills">
        {value.map((addr, idx) => (
          <span
            key={`${addr}-${idx}`}
            className="composer-address-pill"
            onMouseDown={(e) => e.preventDefault()}
            onClick={(e) => e.preventDefault()}
          >
            <span className="composer-address-pill-text">{addr}</span>
            <button
              type="button"
              className="composer-address-pill-remove"
              title="Remove"
              onClick={() => removeAt(idx)}
            >
              x
            </button>
          </span>
        ))}
      </div>

      <input
        ref={inputRef}
        id={fieldId}
        type="text"
        className={className}
        placeholder={placeholder}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ";" || e.key === ",") {
            e.preventDefault();
            commit();
          } else if (e.key === "Backspace" && !draft) {
            if (value.length) onChange(value.slice(0, -1));
          }
        }}
      />
    </div>
  );
}
