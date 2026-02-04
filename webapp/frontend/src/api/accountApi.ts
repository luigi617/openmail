// src/api/accountApi.ts
import { requestJSON, toQuery } from './http';
import type {
  AccountRow,
  CreateAppAccountPayload,
  CreateOAuth2AccountPayload,
  UpdateAccountMetaPayload,
  UpdateSecretsPayload,
} from '../types/accountApi';

export const AccountApi = {

  // GET /api/accounts
  async listAccounts(): Promise<AccountRow[]> {
    return requestJSON<AccountRow[]>('/api/accounts');
  },

  // POST /api/accounts/app
  async createOrUpdateAppAccount(
    payload: CreateAppAccountPayload
  ): Promise<{ status: string; account_id: number; account: AccountRow }> {
    return requestJSON<{ status: string; account_id: number; account: AccountRow }>(
      '/api/accounts/app',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }
    );
  },

  // POST /api/accounts/oauth2
  async createOrUpdateOAuth2Account(
    payload: CreateOAuth2AccountPayload
  ): Promise<{ status: string; account_id: number; authorize_url: string; account: AccountRow }> {
    return requestJSON<{ status: string; account_id: number; authorize_url: string; account: AccountRow }>(
      '/api/accounts/oauth2',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }
    );
  },

  // POST /api/accounts/:id/oauth2/authorize?redirect_uri=...&scopes=...
    async startOAuthExistingAccount(
    accountId: number,
    redirectUri: string,
    scopes?: string
    ): Promise<{ status: string; authorize_url: string }> {
    const qs = toQuery({ redirect_uri: redirectUri, scopes });
    return requestJSON<{ status: string; authorize_url: string }>(
        `/api/accounts/${accountId}/oauth2/authorize${qs}`,
        { method: 'POST' }
    );
    },

  // PATCH /api/accounts/:id
  async updateAccountMeta(
    accountId: number,
    payload: UpdateAccountMetaPayload
  ): Promise<{ status: string; account: AccountRow }> {
    return requestJSON<{ status: string; account: AccountRow }>(`/api/accounts/${accountId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  // PATCH /api/accounts/:id/secrets
  async updateAccountSecrets(
    accountId: number,
    payload: UpdateSecretsPayload
  ): Promise<{ status: string; account: AccountRow }> {
    return requestJSON<{ status: string; account: AccountRow }>(`/api/accounts/${accountId}/secrets`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  // DELETE /api/accounts/:id
  async deleteAccount(accountId: number): Promise<{ status: string }> {
    return requestJSON<{ status: string }>(`/api/accounts/${accountId}`, { method: 'DELETE' });
  },

  // POST /api/accounts/reload (optional; you added it server-side)
  async reload(): Promise<{ status: string }> {
    return requestJSON<{ status: string }>('/api/accounts/reload', { method: 'POST' });
  },
};
