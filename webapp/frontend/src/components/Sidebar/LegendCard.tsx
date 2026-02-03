// src/components/Sidebar/LegendCard.tsx
import { useMemo } from 'react';

export type LegendCardProps = {
  accounts: string[];
  colorMap: Record<string, string>;
  activeAccounts: string[];
  onToggleAccount: (account: string) => void;
};

export default function LegendCard(props: LegendCardProps) {
  const active = useMemo(() => new Set(props.activeAccounts || []), [props.activeAccounts]);

  return (
    <section className="card legend-box">
      <div className="legend-header">
        <h2>Legend</h2>
      </div>

      <div id="legend-list" className="legend-list">
        {props.accounts.map((account) => {
          const color = props.colorMap[account] || '#9ca3af';
          const isActive = active.has(account);

          return (
            <div
              key={account}
              className={`legend-item ${isActive ? 'active' : ''}`}
              data-key={account}
              onClick={() => props.onToggleAccount(account)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') props.onToggleAccount(account);
              }}
              role="button"
              tabIndex={0}
            >
              <span className="legend-color-dot" style={{ background: color }} />
              <span>{account}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
