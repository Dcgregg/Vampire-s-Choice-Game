import React from 'react';
import { History } from 'lucide-react';
import { AdminReviewApproval } from '../../sync/cloudClient';

export const ApprovalHistory: React.FC<{ history?: AdminReviewApproval[] }> = ({ history = [] }) => {
  if (history.length === 0) return null;
  return <section className="mt-4 rounded border border-white/10 bg-black/15 p-3" aria-label="Approval history"><p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#c5a059]"><History className="h-4 w-4" />Approval history</p><ul className="mt-2 grid gap-1 text-xs text-stone-400">{[...history].reverse().map((approval, index) => <li key={`${approval.approvedAt}-${index}`}>Revision {approval.approvedRevision} approved by {approval.approvedBy} on {new Date(approval.approvedAt).toLocaleString()}.</li>)}</ul></section>;
};
