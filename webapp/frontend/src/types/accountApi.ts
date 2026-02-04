export type AccountRow = {
  id: number;
  provider: 'gmail' | 'outlook' | 'yahoo' | 'icloud';
  email: string;
  auth_method: 'app' | 'oauth2' | 'no-auth';
  has_password: boolean;
  has_client: boolean;
  has_refresh_token: boolean;
  created_at: string;
  updated_at: string;
};

export type CreateAppAccountPayload = {
  provider: AccountRow['provider'];
  email: string;
  password: string;
};

export type CreateOAuth2AccountPayload = {
  provider: Exclude<AccountRow['provider'], 'icloud'>;
  email: string;
  client_id: string;
  client_secret: string;
  redirect_uri: string;
  scopes?: string;
};

export type UpdateAccountMetaPayload = {
  provider?: AccountRow['provider'];
  email?: string;
  auth_method?: AccountRow['auth_method'];
};

export type UpdateSecretsPayload = {
  password?: string;
  client_id?: string;
  client_secret?: string;
  clear_refresh_token?: boolean;
};