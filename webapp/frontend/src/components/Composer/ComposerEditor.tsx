// src/components/Composer/ComposerEditor.tsx
import { useEffect, useRef } from 'react';

export type ComposerEditorProps = {
  value: string;
  onChange: (html: string) => void;
};

function isMac() {
  return typeof navigator !== 'undefined' && /Mac|iPhone|iPad|iPod/.test(navigator.platform);
}

function normalizePlainTextToHtml(text: string) {
  // Keep multiple spaces and newlines reasonably.
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

  // Convert newlines to <br>.
  return escaped.replace(/\r\n|\r|\n/g, '<br>');
}

function insertHtmlAtSelection(html: string) {
  // execCommand is deprecated but still the most compatible way for contentEditable insertion.
  // Fallback to Range if execCommand fails.
  try {
    if (document.queryCommandSupported?.('insertHTML')) {
      const ok = document.execCommand('insertHTML', false, html);
      if (ok) return;
    }
  } catch {
    // ignore and fall back
  }

  const sel = window.getSelection?.();
  if (!sel || sel.rangeCount === 0) return;

  const range = sel.getRangeAt(0);
  range.deleteContents();

  const temp = document.createElement('div');
  temp.innerHTML = html;

  const frag = document.createDocumentFragment();
  let node: ChildNode | null;
  // eslint-disable-next-line no-cond-assign
  while ((node = temp.firstChild)) frag.appendChild(node);

  const lastNode = frag.lastChild;
  range.insertNode(frag);

  // Move caret after inserted content
  if (lastNode) {
    const newRange = document.createRange();
    newRange.setStartAfter(lastNode);
    newRange.collapse(true);
    sel.removeAllRanges();
    sel.addRange(newRange);
  }
}

function sanitizePastedHtml(html: string) {
  // “Common sense” sanitation:
  // - remove scripts/iframes/styles/links/meta
  // - remove inline event handlers (on*)
  // - remove javascript: URLs
  // - keep basic formatting + inline styles (lightly filtered)
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');

  // Remove obviously dangerous/undesirable nodes
  const blocked = doc.querySelectorAll(
    'script, iframe, object, embed, link, meta, style, form, input, button, textarea, select'
  );
  blocked.forEach((n) => n.remove());

  const allowedStyleProps = new Set([
    'font-weight',
    'font-style',
    'text-decoration',
    'color',
    'background-color',
    'font-size',
    'font-family',
    'text-align',
    'white-space',
  ]);

  const walk = (node: Element) => {
    // Remove event handlers + dangerous attributes
    for (const attr of Array.from(node.attributes)) {
      const name = attr.name.toLowerCase();
      const value = attr.value;

      if (name.startsWith('on')) {
        node.removeAttribute(attr.name);
        continue;
      }

      if ((name === 'href' || name === 'src') && /^\s*javascript:/i.test(value)) {
        node.removeAttribute(attr.name);
        continue;
      }

      // Filter style down to a safe-ish subset
      if (name === 'style') {
        const kept: string[] = [];
        value.split(';').forEach((decl) => {
          const [rawProp, ...rest] = decl.split(':');
          if (!rawProp || rest.length === 0) return;
          const prop = rawProp.trim().toLowerCase();
          const val = rest.join(':').trim();
          if (!prop) return;

          if (allowedStyleProps.has(prop)) kept.push(`${prop}: ${val}`);
        });

        if (kept.length) node.setAttribute('style', kept.join('; '));
        else node.removeAttribute('style');
        continue;
      }

      // Drop some noisy attributes commonly from Google Docs/Word/etc.
      // (Note: "data-*" can't be matched like this; we only drop class/id here.)
      if (name === 'class' || name === 'id') {
        node.removeAttribute(attr.name);
      }
    }

    // Recurse
    for (const child of Array.from(node.children)) walk(child);
  };

  for (const el of Array.from(doc.body.children)) walk(el);

  return doc.body.innerHTML;
}

export default function ComposerEditor({ value, onChange }: ComposerEditorProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  // Track whether user is actively editing to avoid caret/selection resets.
  const isFocusedRef = useRef(false);
  const lastEmittedHtmlRef = useRef<string>(value);

  // Flag set by Cmd/Ctrl+Shift+V (detected in onKeyDown)
  // so the next paste is forced to plain text.
  const plainPasteNextRef = useRef(false);

  // Sync external value into the editor ONLY when not focused (or on first mount).
  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    // If parent updates value because *we* emitted it, don't fight the DOM.
    if (value === lastEmittedHtmlRef.current) return;

    // If user is typing/pasting right now, don't clobber selection.
    if (isFocusedRef.current) return;

    if (el.innerHTML !== value) {
      el.innerHTML = value;
    }
  }, [value]);

  const emitChange = () => {
    const html = ref.current?.innerHTML ?? '';
    lastEmittedHtmlRef.current = html;
    onChange(html);
  };

  return (
    <div className="composer-editor">
      <div
        ref={ref}
        id="composer-body"
        contentEditable
        role="textbox"
        aria-multiline="true"
        spellCheck
        suppressContentEditableWarning
        onFocus={() => {
          isFocusedRef.current = true;
        }}
        onBlur={() => {
          isFocusedRef.current = false;
          // Ensure final value is emitted on blur (common sense behavior).
          emitChange();
        }}
        onInput={() => {
          emitChange();
        }}
        onKeyDown={(e) => {
          const mod = isMac() ? e.metaKey : e.ctrlKey;

          // Cmd/Ctrl+Shift+V => plain paste
          if (mod && e.shiftKey && (e.key === 'V' || e.key === 'v')) {
            plainPasteNextRef.current = true;

            // If Clipboard API is available/allowed, do plain paste immediately for consistency.
            const canRead =
              typeof navigator !== 'undefined' &&
              'clipboard' in navigator &&
              'readText' in navigator.clipboard;

            if (canRead) {
              e.preventDefault();
              navigator.clipboard
                .readText()
                .then((t) => {
                  insertHtmlAtSelection(normalizePlainTextToHtml(t));
                  emitChange();
                })
                .catch(() => {
                  // If readText fails, we'll fall back to handling onPaste with the flag.
                });
            }
          }
        }}
        onPaste={(e) => {
          const dt = e.clipboardData;
          if (!dt) return;

          const html = dt.getData('text/html');
          const text = dt.getData('text/plain');

          // We handle paste ourselves for consistent behavior.
          e.preventDefault();

          const forcePlain = plainPasteNextRef.current;
          plainPasteNextRef.current = false;

          if (forcePlain || !html) {
            insertHtmlAtSelection(normalizePlainTextToHtml(text));
            emitChange();
            return;
          }

          const cleaned = sanitizePastedHtml(html);
          insertHtmlAtSelection(cleaned);
          emitChange();
        }}
      />
    </div>
  );
}
