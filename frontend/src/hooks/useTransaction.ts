/** Hook for transaction CRUD and participant management. */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { Transaction, ParticipantRole, TransactionInvitation } from '../types/transaction';
import type { InvitationResult, TransactionCompletionResult } from '../api/transactions';
import {
  listTransactions,
  getTransaction,
  createTransaction,
  updateTransaction,
  deleteTransaction,
  addParticipant,
  removeParticipant,
  autoFillTransaction,
  getTransactionCompletion,
  createInvitation,
  listTransactionInvitations,
  resendInvitation,
  revokeInvitation,
  linkExtractionToTransaction,
  unlinkExtractionFromTransaction,
  fetchTransactionExtractions,
  type CreateTransactionPayload,
} from '../api/transactions';

interface UseTransactionListReturn {
  transactions: Transaction[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  create: (data: CreateTransactionPayload) => Promise<Transaction>;
  remove: (id: string) => Promise<void>;
}

export function useTransactionList(): UseTransactionListReturn {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listTransactions();
      setTransactions(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load transactions');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const create = useCallback(async (data: CreateTransactionPayload) => {
    const txn = await createTransaction(data);
    await refresh();
    return txn;
  }, [refresh]);

  const remove = useCallback(async (id: string) => {
    await deleteTransaction(id);
    await refresh();
  }, [refresh]);

  return { transactions, loading, error, refresh, create, remove };
}


interface UseTransactionDetailReturn {
  transaction: Transaction | null;
  completion: TransactionCompletionResult | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  update: (data: Parameters<typeof updateTransaction>[1]) => Promise<void>;
  addParticipantByEmail: (email: string, role: ParticipantRole, name?: string) => Promise<void>;
  removeParticipantById: (userId: string) => Promise<void>;
  sendInvitation: (email: string, role: ParticipantRole, name?: string) => Promise<InvitationResult>;
  invitations: TransactionInvitation[];
  resendTransactionInvitation: (invitationId: string) => Promise<InvitationResult>;
  revokeTransactionInvitation: (invitationId: string) => Promise<InvitationResult>;
  runAutoFill: () => Promise<string[]>;
  extractions: Array<{
    id: string;
    filename: string;
    mode: string;
    overall_confidence: number;
    pages_processed: number;
    created_at: string | null;
    document_type?: string | null;
    document_form_id?: string | null;
    document_title?: string | null;
    document_revision?: string | null;
    support_level?: string | null;
  }>;
  linkExtraction: (extractionId: string) => Promise<void>;
  unlinkExtraction: (extractionId: string) => Promise<void>;
}

export function useTransactionDetail(id: string | undefined): UseTransactionDetailReturn {
  const [transaction, setTransaction] = useState<Transaction | null>(null);
  const [completion, setCompletion] = useState<TransactionCompletionResult | null>(null);
  const [invitations, setInvitations] = useState<TransactionInvitation[]>([]);
  const [extractions, setExtractions] = useState<Array<{
    id: string;
    filename: string;
    mode: string;
    overall_confidence: number;
    pages_processed: number;
    created_at: string | null;
    document_type?: string | null;
    document_form_id?: string | null;
    document_title?: string | null;
    document_revision?: string | null;
    support_level?: string | null;
  }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const initialLoadDone = useRef(false);

  const refresh = useCallback(async () => {
    if (!id) return;
    try {
      // Only show full-page loading on the initial fetch; background refreshes
      // (after mutations) update state silently to avoid unmounting tab children.
      if (!initialLoadDone.current) setLoading(true);
      setError(null);
      const [txn, comp, exts, invitationList] = await Promise.all([
        getTransaction(id),
        getTransactionCompletion(id),
        fetchTransactionExtractions(id),
        listTransactionInvitations(id).catch(() => []),
      ]);
      setTransaction(txn);
      setCompletion(comp);
      setExtractions(exts);
      setInvitations(invitationList);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load transaction');
    } finally {
      setLoading(false);
      initialLoadDone.current = true;
    }
  }, [id]);

  useEffect(() => { refresh(); }, [refresh]);

  const update = useCallback(async (data: Parameters<typeof updateTransaction>[1]) => {
    if (!id) return;
    await updateTransaction(id, data);
    await refresh();
  }, [id, refresh]);

  const addParticipantByEmail = useCallback(async (email: string, role: ParticipantRole, name?: string) => {
    if (!id) return;
    await addParticipant(id, { email, role, name });
    await refresh();
  }, [id, refresh]);

  const removeParticipantById = useCallback(async (userId: string) => {
    if (!id) return;
    await removeParticipant(id, userId);
    await refresh();
  }, [id, refresh]);

  const sendInvitation = useCallback(async (email: string, role: ParticipantRole, name?: string) => {
    if (!id) throw new Error('No transaction ID');
    const result = await createInvitation({
      email,
      role,
      transaction_id: id,
      name,
    });
    await refresh();
    return result;
  }, [id, refresh]);

  const resendTransactionInvitation = useCallback(async (invitationId: string) => {
    const result = await resendInvitation(invitationId);
    await refresh();
    return result;
  }, [refresh]);

  const revokeTransactionInvitation = useCallback(async (invitationId: string) => {
    const result = await revokeInvitation(invitationId);
    await refresh();
    return result;
  }, [refresh]);

  const runAutoFill = useCallback(async () => {
    if (!id) return [];
    const result = await autoFillTransaction(id);
    setTransaction(result.transaction);
    return result.filled_fields;
  }, [id]);

  const linkExtraction = useCallback(async (extractionId: string) => {
    if (!id) return;
    await linkExtractionToTransaction(id, extractionId);
    await refresh();
  }, [id, refresh]);

  const unlinkExtraction = useCallback(async (extractionId: string) => {
    if (!id) return;
    await unlinkExtractionFromTransaction(id, extractionId);
    await refresh();
  }, [id, refresh]);

  return {
    transaction,
    completion,
    extractions,
    loading,
    error,
    refresh,
    update,
    addParticipantByEmail,
    removeParticipantById,
    sendInvitation,
    invitations,
    resendTransactionInvitation,
    revokeTransactionInvitation,
    runAutoFill,
    linkExtraction,
    unlinkExtraction,
  };
}
