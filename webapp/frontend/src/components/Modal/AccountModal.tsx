// src/components/Modal/AccountsModal.tsx
import { useEffect, useMemo, useState } from 'react';
import type { AccountRow } from '../../types/accountApi';
import { AccountApi } from '../../api/accountApi';
import CloseIcon from '@/assets/svg/close.svg?react';
import { EmailApi } from '../../api/emailApi';

type Props = {
  open: boolean;
  onClose: () => void;
  onAccountsChanged?: () => void;
};

type Mode = 'list' | 'create' | 'edit';

type ConnectedMap = Record<string, { ok: boolean; detail: string }>;

function isConnected(a: AccountRow, connectedById: ConnectedMap) {
  return connectedById[String(a.id)]?.ok ?? false;
}

export default function AccountsModal({ open, onClose, onAccountsChanged }: Props) {
  const [mode, setMode] = useState<Mode>('list');
  const [accounts, setAccounts] = useState<AccountRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [selected, setSelected] = useState<AccountRow | null>(null);

  // health-check connection status (imap/smtp)
  const [connectedById, setConnectedById] = useState<ConnectedMap>({});

  // create/edit form state
  const [provider, setProvider] = useState<AccountRow['provider']>('gmail');
  const [email, setEmail] = useState('');
  const [authMethod, setAuthMethod] = useState<AccountRow['auth_method']>('app');

  const [password, setPassword] = useState('');
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [redirectUri, setRedirectUri] = useState(`http://localhost:8000/api/accounts/oauth/callback`);
  const [scopes, setScopes] = useState('');

  const connectedCount = useMemo(
    () => accounts.filter((a) => isConnected(a, connectedById)).length,
    [accounts, connectedById]
  );

  async function refresh() {
    setLoading(true);
    setErr(null);
    try {
      const rows = await AccountApi.listAccounts();
      setAccounts(rows);

      // run health checks for each account
      const entries = await Promise.all(
        rows.map(async (a) => {
          try {
            const key = a.email;
            if (a.auth_method === 'app' && !a.has_password) {
              return [String(a.id), { ok: false, detail: "needs app password" }] as const;
            }
            if (a.auth_method === 'oauth2' && !a.has_refresh_token) {
              return [String(a.id), { ok: false, detail: "needs OAuth" }] as const;
            }
            const res = await EmailApi.isAccountConnected(key);
            return [String(a.id), { ok: !!res.result, detail: res.detail }] as const;
          } catch (e: any) {
            return [String(a.id), { ok: false, detail: e?.message ?? 'health check failed' }] as const;
          }
        })
      );

      setConnectedById(Object.fromEntries(entries));
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    } finally {
      setLoading(false);
    }
  }

  // check connection status when modal opens
  useEffect(() => {
    if (!open) return;
    setMode('list');
    setSelected(null);
    void refresh();
  }, [open]);

  function resetForm() {
    setProvider('gmail');
    setEmail('');
    setAuthMethod('app');
    setPassword('');
    setClientId('');
    setClientSecret('');
    setScopes('');
    setRedirectUri(`http://localhost:8000/api/accounts/oauth/callback`);
  }

  function beginCreate() {
    resetForm();
    setMode('create');
    setSelected(null);
    setErr(null);
  }

  function beginEdit(a: AccountRow) {
    setSelected(a);
    setMode('edit');
    setErr(null);

    setProvider(a.provider);
    setEmail(a.email);
    setAuthMethod(a.auth_method);

    // secrets are not returned for security, so leave blank
    setPassword('');
    setClientId('');
    setClientSecret('');
    setScopes('');
    setRedirectUri(`http://localhost:8000/api/accounts/oauth/callback`);
  }

  async function handleSave() {
    setErr(null);

    try {
      if (authMethod === 'app') {
        if (!email.trim()) throw new Error('Email is required');
        if (!password.trim() && mode === 'create') throw new Error('Password is required');

        if (mode === 'create') {
          await AccountApi.createOrUpdateAppAccount({ provider, email, password });
        } else {
          if (!selected) throw new Error('No account selected');
          if (!password.trim()) throw new Error('Enter new password to update');
          await AccountApi.updateAccountSecrets(selected.id, { password });
        }
      } else if (authMethod === 'oauth2') {
        if (provider === 'icloud') throw new Error('iCloud does not support OAuth2');
        if (!email.trim()) throw new Error('Email is required');

        if (mode === 'create') {
          if (!clientId.trim()) throw new Error('Client ID is required');
          if (!clientSecret.trim()) throw new Error('Client secret is required');
          if (!redirectUri.trim()) throw new Error('Redirect URI is required');

          const res = await AccountApi.createOrUpdateOAuth2Account({
            provider: provider as Exclude<AccountRow['provider'], 'icloud'>,
            email,
            client_id: clientId,
            client_secret: clientSecret,
            redirect_uri: redirectUri,
            scopes: scopes.trim() ? scopes.trim() : undefined,
          });

          window.open(res.authorize_url, '_blank', 'noopener,noreferrer');
        } else {
          if (!selected) throw new Error('No account selected');
          const patch: any = {};
          if (clientId.trim()) patch.client_id = clientId.trim();
          if (clientSecret.trim()) patch.client_secret = clientSecret.trim();
          if (Object.keys(patch).length === 0) throw new Error('Enter client_id and/or client_secret to update');
          await AccountApi.updateAccountSecrets(selected.id, patch);
        }
      } else {
        throw new Error('Unsupported auth method');
      }

      await refresh();
      onAccountsChanged?.();
      setMode('list');
      setSelected(null);
      resetForm();
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    }
  }

  async function handleDelete(a: AccountRow) {
    const ok = window.confirm(`Delete account "${a.email}"?`);
    if (!ok) return;

    setErr(null);
    try {
      await AccountApi.deleteAccount(a.id);
      await refresh();
      onAccountsChanged?.();
      if (selected?.id === a.id) setSelected(null);
      setMode('list');
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    }
  }

  async function handleReconnect(a: AccountRow) {
    setErr(null);
    try {
      if (a.auth_method !== 'oauth2') return;
      const res = await AccountApi.startOAuthExistingAccount(
        a.id,
        redirectUri,
        scopes.trim() ? scopes.trim() : undefined
      );
      window.open(res.authorize_url, '_blank', 'noopener,noreferrer');
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    }
  }

  if (!open) return null;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal">
        <div className="modal-header">
          <div>
            <h3>Accounts</h3>
            <div className="muted">{loading ? 'Loading…' : `${connectedCount}/${accounts.length} connected`}</div>
          </div>

          <div className="row" style={{ gap: 8 }}>
            <button className="secondary" onClick={() => void refresh()} disabled={loading}>
              Refresh status
            </button>
            <button
              type="button"
              className="account-header-link"
              title="Close"
              aria-label="Close"
              onClick={onClose}
            >
              <CloseIcon className="icon" aria-hidden />
            </button>
          </div>
        </div>

        {err ? <div className="modal-error">{err}</div> : null}

        {mode === 'list' ? (
          <div className="modal-body">
            <div className="row" style={{ justifyContent: 'space-between', marginBottom: 10 }}>
              <button className="primary" onClick={beginCreate}>
                Add account
              </button>
            </div>

            {accounts.length === 0 ? (
              <div className="muted">No accounts yet.</div>
            ) : (
              <div className="accounts-list">
                {accounts.map((a) => {
                  const status = connectedById[String(a.id)];
                  const connected = isConnected(a, connectedById);

                  return (
                    <div key={a.id} className="accounts-row">
                      <div className="accounts-main">
                        <div className="accounts-title">
                          <strong>{a.email}</strong>
                          <span className={`pill ${connected ? 'ok' : 'bad'}`}>
                            {connected ? 'Connected' : 'Not connected'}
                          </span>
                        </div>

                        <div className="muted">
                          {a.provider} • {a.auth_method}
                          {status ? ` • ${status.detail}` : ' • status unknown'}
                        </div>
                      </div>

                      <div className="accounts-actions">
                        {/* OAuth2: connect/reconnect opens consent flow */}
                        {a.auth_method === 'oauth2' ? (
                          <button className="secondary" onClick={() => void handleReconnect(a)}>
                            {connected ? 'Reconnect' : 'Connect'}
                          </button>
                        ) : null}

                        {/* App password: if not connected, guide them to enter app password */}
                        {a.auth_method === 'app' && !connected ? (
                          <button className="secondary" onClick={() => beginEdit(a)}>
                            Connect
                          </button>
                        ) : null}

                        <button className="secondary" onClick={() => beginEdit(a)}>
                          Edit
                        </button>
                        <button className="secondary" onClick={() => void handleDelete(a)}>
                          Remove
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ) : (
          <div className="modal-body">
            <div className="row" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
              <strong>{mode === 'create' ? 'Add account' : `Edit: ${selected?.email}`}</strong>
              <button
                className="secondary"
                onClick={() => {
                  setMode('list');
                  setSelected(null);
                  resetForm();
                  setErr(null);
                }}
              >
                Back
              </button>
            </div>

            <div className="form-grid">
              <label>
                Provider
                <select value={provider} onChange={(e) => setProvider(e.target.value as any)} disabled={mode === 'edit'}>
                  <option value="gmail">gmail</option>
                  <option value="outlook">outlook</option>
                  <option value="yahoo">yahoo</option>
                  <option value="icloud">icloud</option>
                </select>
              </label>

              <label>
                Email
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={mode === 'edit'}
                />
              </label>

              <label>
                Auth method
                <select
                  value={authMethod}
                  onChange={(e) => setAuthMethod(e.target.value as any)}
                  disabled={mode === 'edit'}
                >
                  <option value="app">app</option>
                  <option value="oauth2">oauth2</option>
                  <option value="no-auth">no-auth</option>
                </select>
              </label>
            </div>

            {authMethod === 'app' ? (
              <div className="form-grid" style={{ marginTop: 10 }}>
                <label style={{ gridColumn: '1 / -1' }}>
                  App password
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder={
                      mode === 'edit'
                        ? selected?.has_password
                          ? 'Enter new password to rotate'
                          : 'Enter app password to connect'
                        : ''
                    }
                  />
                  {mode === 'edit' && selected && !connectedById[String(selected.id)]?.ok ? (
                    <div className="muted">This account isn’t connected yet — enter the app password and click Save.</div>
                  ) : null}
                </label>
              </div>
            ) : null}

            {authMethod === 'oauth2' ? (
              <>
                <div className="form-grid" style={{ marginTop: 10 }}>
                  <label>
                    Client ID
                    <input
                      type="password"
                      value={clientId}
                      onChange={(e) => setClientId(e.target.value)}
                      placeholder={mode === 'edit' ? 'Enter to rotate (optional)' : ''}
                    />
                  </label>

                  <label>
                    Client secret
                    <input
                      type="password"
                      value={clientSecret}
                      onChange={(e) => setClientSecret(e.target.value)}
                      placeholder={mode === 'edit' ? 'Enter to rotate (optional)' : ''}
                    />
                  </label>

                  <label style={{ gridColumn: '1 / -1' }}>
                    Redirect URI
                    <input type="text" value={redirectUri} onChange={(e) => setRedirectUri(e.target.value)} />
                  </label>

                  <label style={{ gridColumn: '1 / -1' }}>
                    Scopes (optional)
                    <input
                      type="text"
                      value={scopes}
                      onChange={(e) => setScopes(e.target.value)}
                      placeholder="leave blank to use backend defaults"
                    />
                  </label>
                </div>

                {mode === 'edit' && selected ? (
                  <div className="row" style={{ gap: 8, marginTop: 10 }}>
                    <button
                      className="secondary"
                      onClick={async () => {
                        setErr(null);
                        try {
                          await AccountApi.updateAccountSecrets(selected.id, { clear_refresh_token: true });
                          await refresh();
                          onAccountsChanged?.();
                        } catch (e: any) {
                          setErr(e?.message ?? String(e));
                        }
                      }}
                    >
                      Clear refresh token
                    </button>

                    <button className="secondary" onClick={() => void handleReconnect(selected)}>
                      Reconnect (OAuth)
                    </button>
                  </div>
                ) : null}
              </>
            ) : null}

            <div className="row" style={{ justifyContent: 'flex-end', gap: 8, marginTop: 14 }}>
              <button className="secondary" onClick={() => void refresh()}>
                Re-check status
              </button>
              <button className="primary" onClick={handleSave}>
                Save
              </button>
            </div>

            <div className="muted" style={{ marginTop: 10 }}>
              Connected status updates when you click “Refresh status” (or reopen this modal).
              For OAuth2, click “Connect” to complete the consent flow.
              For app-password accounts, “Connect” means entering an app password so IMAP/SMTP become active.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
