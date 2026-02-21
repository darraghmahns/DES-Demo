/** Hook for transaction CRUD and participant management. */

import { useCallback, useEffect, useState } from 'react';
import type { Transaction, ParticipantRole } from '../types/transaction';
import type { TransactionCompletionResult } from '../api/transactions';
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
  sendInvitation: (email: string, role: ParticipantRole, name?: string) => Promise<string>;
  runAutoFill: () => Promise<string[]>;
}

export function useTransactionDetail(id: string | undefined): UseTransactionDetailReturn {
  const [transaction, setTransaction] = useState<Transaction | null>(null);
  const [completion, setCompletion] = useState<TransactionCompletionResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!id) return;
    try {
      setLoading(true);
      setError(null);
      const [txn, comp] = await Promise.all([
        getTransaction(id),
        getTransactionCompletion(id),
      ]);
      setTransaction(txn);
      setCompletion(comp);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load transaction');
    } finally {
      setLoading(false);
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
    return result.signed_token;
  }, [id, refresh]);

  const runAutoFill = useCallback(async () => {
    if (!id) return [];
    const result = await autoFillTransaction(id);
    setTransaction(result.transaction);
    return result.filled_fields;
  }, [id]);

  return {
    transaction,
    completion,
    loading,
    error,
    refresh,
    update,
    addParticipantByEmail,
    removeParticipantById,
    sendInvitation,
    runAutoFill,
  };
}
