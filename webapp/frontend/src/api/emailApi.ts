// src/api/emailApi.ts
import { requestJSON } from './http';
import type { MailboxData, EmailMessage, EmailOverview } from '../types/email';
import type { EmailRef } from '../types/shared';
import type {
  ForwardParams,
  OverviewParams,
  OverviewResponse,
  ReplyParams,
  SaveDraftParams,
  SendEmailParams,
} from '../types/api';

function buildEmailUrl(account: string, mailbox: string, uid: string, suffix = '') {
  const a = encodeURIComponent(account);
  const m = encodeURIComponent(mailbox);
  const u = encodeURIComponent(uid);
  return `/api/accounts/${a}/mailboxes/${m}/emails/${u}${suffix}`;
}

function appendMany(form: FormData, key: string, values?: string[]) {
  for (const v of values ?? []) form.append(key, v);
}

function appendFiles(form: FormData, key: string, files?: File[]) {
  for (const f of files ?? []) form.append(key, f);
}

function buildReplyForm(args: ReplyParams): FormData {
  const form = new FormData();

  form.append('text', args.text || '');
  if (args.html) form.append('html', args.html);
  if (args.fromAddr) form.append('from_addr', args.fromAddr);
  form.append('quote_original', args.quoteOriginal ? 'true' : 'false');
  if (args.subject) form.append('subject', args.subject);

  appendMany(form, 'to', args.to);
  appendMany(form, 'cc', args.cc);
  appendMany(form, 'bcc', args.bcc);
  appendMany(form, 'reply_to', args.replyTo);

  // Priority is always valid in your app now (high|medium|low),
  // but keep guard in case caller omits.
  if (args.priority) form.append('priority', args.priority);

  appendFiles(form, 'attachments', args.attachments);

  return form;
}

async function replyImpl<T>(
  endpointSuffix: '/reply' | '/reply-all',
  args: ReplyParams
): Promise<T> {
  const url = buildEmailUrl(args.account, args.mailbox, args.uid.toString(), endpointSuffix);
  const form = buildReplyForm(args);
  return requestJSON<T>(url, { method: 'POST', body: form });
}

export const EmailApi = {
  // GET /api/emails/mailbox
  async getMailboxes(): Promise<MailboxData> {
    return requestJSON<MailboxData>('/api/emails/mailbox');
  },

  // GET /api/emails/overview?mailbox=&limit=&cursor=&accounts=a&accounts=b
  async getOverview(params: OverviewParams): Promise<OverviewResponse<EmailOverview>> {
    const sp = new URLSearchParams();

    if (params.mailbox) sp.set('mailbox', params.mailbox);
    if (params.limit != null) sp.set('limit', String(params.limit));
    if (params.search_query != null) sp.set('search_query', String(params.search_query));
    if (params.search_mode != null) sp.set('search_mode', String(params.search_mode));
    if (params.cursor) sp.set('cursor', params.cursor);

    // Preserve existing behavior: only include accounts when NOT using cursor.
    if (!params.cursor && params.accounts?.length) {
      for (const acc of params.accounts) sp.append('accounts', acc);
    }

    const qs = sp.toString();
    const url = `/api/emails/overview${qs ? `?${qs}` : ''}`;
    return requestJSON<OverviewResponse<EmailOverview>>(url);
  },

  // GET single email
  async getEmail(key: EmailRef): Promise<EmailMessage> {
    return requestJSON<EmailMessage>(buildEmailUrl(key.account, key.mailbox, key.uid.toString()));
  },

  // POST archive
  async archiveEmail<T>(key: EmailRef): Promise<T> {
    return requestJSON<T>(buildEmailUrl(key.account, key.mailbox, key.uid.toString(), '/archive'), {
      method: 'POST',
    });
  },

  // DELETE
  async deleteEmail<T>(key: EmailRef): Promise<T> {
    return requestJSON<T>(buildEmailUrl(key.account, key.mailbox, key.uid.toString()), {
      method: 'DELETE',
    });
  },

  // POST move (FormData destination_mailbox)
  async moveEmail<T>(args: EmailRef & { destinationMailbox: string }): Promise<T> {
    const form = new FormData();
    form.append('destination_mailbox', args.destinationMailbox);

    return requestJSON<T>(buildEmailUrl(args.account, args.mailbox, args.uid.toString(), '/move'), {
      method: 'POST',
      body: form,
    });
  },

  // POST reply
  async replyEmail<T>(args: ReplyParams): Promise<T> {
    return replyImpl<T>('/reply', args);
  },

  // POST reply-all
  async replyAllEmail<T>(args: ReplyParams): Promise<T> {
    return replyImpl<T>('/reply-all', args);
  },

  // POST forward
  async forwardEmail<T>(args: ForwardParams): Promise<T> {
    const url = buildEmailUrl(args.account, args.mailbox, args.uid.toString(), '/forward');
    const form = new FormData();

    appendMany(form, 'to', args.to);

    if (args.text != null) form.append('text', args.text);
    if (args.html) form.append('html', args.html);
    if (args.fromAddr) form.append('from_addr', args.fromAddr);

    form.append('include_original', args.includeOriginal ? 'true' : 'false');
    form.append('include_attachments', args.includeAttachments !== false ? 'true' : 'false');

    if (args.subject) form.append('subject', args.subject);

    appendMany(form, 'cc', args.cc);
    appendMany(form, 'bcc', args.bcc);
    appendMany(form, 'reply_to', args.replyTo);
    if (args.priority) form.append('priority', args.priority);

    appendFiles(form, 'attachments', args.attachments);

    return requestJSON<T>(url, { method: 'POST', body: form });
  },

  // POST /api/accounts/:a/send
  async sendEmail<T>(args: SendEmailParams): Promise<T> {
    const a = encodeURIComponent(args.account);
    const url = `/api/accounts/${a}/send`;
    const form = new FormData();

    form.append('subject', args.subject || '');
    appendMany(form, 'to', args.to);
    if (args.fromAddr) form.append('from_addr', args.fromAddr);
    appendMany(form, 'cc', args.cc);
    appendMany(form, 'bcc', args.bcc);

    if (args.text != null) form.append('text', args.text);
    if (args.html) form.append('html', args.html);

    appendMany(form, 'reply_to', args.replyTo);
    if (args.priority) form.append('priority', args.priority);

    appendFiles(form, 'attachments', args.attachments);

    return requestJSON<T>(url, { method: 'POST', body: form });
  },

  // POST /api/accounts/:a/draft
  async saveDraft<T>(args: SaveDraftParams): Promise<T> {
    const a = encodeURIComponent(args.account);
    const url = `/api/accounts/${a}/draft`;
    const form = new FormData();

    if (args.subject != null) form.append('subject', args.subject);

    appendMany(form, 'to', args.to);
    if (args.fromAddr) form.append('from_addr', args.fromAddr);
    appendMany(form, 'cc', args.cc);
    appendMany(form, 'bcc', args.bcc);

    if (args.text != null) form.append('text', args.text);
    if (args.html) form.append('html', args.html);

    appendMany(form, 'reply_to', args.replyTo);
    if (args.priority) form.append('priority', args.priority);

    if (args.draftsMailbox) form.append('drafts_mailbox', args.draftsMailbox);

    appendFiles(form, 'attachments', args.attachments);

    return requestJSON<T>(url, { method: 'POST', body: form });
  },
};
