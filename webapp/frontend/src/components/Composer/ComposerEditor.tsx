// src/components/Composer/ComposerEditor.tsx
import React, { useEffect, useRef } from "react";

export type ComposerEditorProps = {
  value: string;
  onChange: (html: string) => void;
};

export default function ComposerEditor({ value, onChange }: ComposerEditorProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    if (el.innerHTML !== value) el.innerHTML = value;
  }, [value]);

  return (
    <div className="composer-editor">
      <div
        ref={ref}
        id="composer-body"
        contentEditable
        role="textbox"
        aria-multiline="true"
        spellCheck
        onInput={() => {
          onChange(ref.current?.innerHTML ?? "");
        }}
        suppressContentEditableWarning
      />
    </div>
  );
}
