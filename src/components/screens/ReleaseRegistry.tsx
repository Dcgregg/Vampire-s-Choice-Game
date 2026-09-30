import React from 'react';
import { CheckCircle2, Download, History, MessageSquareText, PackageCheck, Rocket, RotateCcw, ShieldCheck, Users } from 'lucide-react';
import {
  AdminDraft, AdminReleaseVersion, BetaFeedback, BetaReadiness, TrustedContentCompatibility, configureBetaReleaseAccess,
  createAdminReleaseVersion, getAdminReleaseVersion, getAdminReleaseVersions,
  getBetaReleaseAccess, getBetaReleaseFeedback, getBetaReleaseReadiness, getBetaReleaseReport, getNarrativeConversionPreview, getReleasePublicationHandoff, getTrustedContentCompatibility,
  approveReleasePublicationReview, getStagedReleaseReadiness, recordBetaReleaseDecision, selectAdminReleaseVersion,
  stageAdminReleaseVersion, triageBetaReleaseFeedback,
} from '../../sync/cloudClient';

export const ReleaseRegistry: React.FC<{ draft: AdminDraft; onNotice: (message: string) => void }> = ({ draft, onNotice }) => {
  const [releases, setReleases] = React.useState<AdminReleaseVersion[] | null>(null);
  const [working, setWorking] = React.useState(false);
  const [testerEmails, setTesterEmails] = React.useState<Record<string, string>>({});
  const [feedback, setFeedback] = React.useState<Record<string, BetaFeedback[]>>({});
  const [feedbackNotes, setFeedbackNotes] = React.useState<Record<string, string>>({});
  const [decisionNotes, setDecisionNotes] = React.useState<Record<string, string>>({});
  const [publicationNotes, setPublicationNotes] = React.useState<Record<string, string>>({});
  const [betaGates, setBetaGates] = React.useState<Record<string, BetaReadiness>>({});
  const [compatibility, setCompatibility] = React.useState<Record<string, TrustedContentCompatibility>>({});

  const refresh = async () => {
    const next = await getAdminReleaseVersions() ?? [];
    setReleases(next);
    const saved = await Promise.all(next.filter((release) => release.status === 'staged').map(async (release) => [release.releaseId, (await getBetaReleaseAccess(release.releaseId).catch(() => [])).join('\n')] as const));
    setTesterEmails(Object.fromEntries(saved));
  };
  React.useEffect(() => { void refresh().catch(() => setReleases([])); }, []);

  const run = async (action: () => Promise<void>, failure: string) => {
    setWorking(true);
    try { await action(); } catch { onNotice(failure); } finally { setWorking(false); }
  };
  const prepare = () => run(async () => {
    const release = await createAdminReleaseVersion(draft.draftId);
    await refresh();
    onNotice(`Release v${release.version} is frozen in the private registry. It is not live player content.`);
  }, 'Could not create the release version. Approve a valid draft first.');
  const select = (release: AdminReleaseVersion) => run(async () => {
    const rollback = release.status !== 'selected';
    await selectAdminReleaseVersion(release.releaseId, rollback);
    await refresh();
    onNotice(rollback ? `Rolled back the private registry to v${release.version}. No player content changed.` : `Release v${release.version} remains selected for later rollout.`);
  }, 'Could not update the selected release version.');
  const stage = (release: AdminReleaseVersion) => run(async () => {
    await stageAdminReleaseVersion(release.releaseId);
    await refresh();
    onNotice(`Release v${release.version} is available through the flag-gated staging preview only. It cannot read or update player saves.`);
  }, 'Could not stage this version. Add STAGED_RELEASE_PREVIEW=true to this Preview environment, then redeploy.');
  const readiness = (release: AdminReleaseVersion) => run(async () => {
    const result = await getStagedReleaseReadiness(release.releaseId);
    onNotice(`Staging readiness: ${result.sessionCount} sessions, ${result.completedSessionCount} completed routes, ${result.playerSavesTouched} player saves touched, production published: ${result.productionPublished ? 'yes' : 'no'}.`);
  }, 'Could not load the staging readiness report.');
  const betaReadiness = (release: AdminReleaseVersion) => run(async () => {
    const result = await getBetaReleaseReadiness(release.releaseId);
    onNotice(`Private beta: ${result.invitedCount} invited, ${result.sessionCount} sessions, ${result.completedSessionCount} completed routes, ${result.openFeedbackCount} open and ${result.resolvedFeedbackCount} resolved feedback reports. Public release: no.`);
  }, 'Could not load the beta readiness report.');
  const checkBetaGate = (release: AdminReleaseVersion) => run(async () => {
    const result = await getBetaReleaseReadiness(release.releaseId);
    setBetaGates((current) => ({ ...current, [release.releaseId]: result }));
    onNotice(result.readyForDecision ? 'Beta gate is clear for a human release-review decision. This does not publish the story.' : 'Beta gate loaded below. Resolve its listed blockers before release review.');
  }, 'Could not load the beta release gate.');
  const downloadBetaReport = (release: AdminReleaseVersion) => run(async () => {
    const report = await getBetaReleaseReport(release.releaseId);
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `${release.bookId}-beta-report-v${release.version}.json`; link.click(); URL.revokeObjectURL(url);
    onNotice(report.summary.readyForReleaseReview ? 'Downloaded beta report. Its checklist is clear for human release review; the story remains unpublished.' : `Downloaded beta report. Checklist: ${report.summary.sessionCount ? '' : 'no beta sessions; '}${report.summary.openFeedbackCount ? `${report.summary.openFeedbackCount} open feedback item${report.summary.openFeedbackCount === 1 ? '' : 's'}` : 'no open feedback'}.`);
  }, 'Could not create the private beta report.');
  const betaAccess = (release: AdminReleaseVersion, disable = false) => {
    const emails = disable ? [] : (testerEmails[release.releaseId] ?? '').split(/[\n,;]+/).map((email) => email.trim()).filter(Boolean);
    if (!disable && !emails.length) { onNotice('Enter at least one tester email first.'); return; }
    return run(async () => {
      const result = await configureBetaReleaseAccess(release.releaseId, emails);
      await refresh();
      onNotice(result.enabled ? `Private beta enabled for ${result.invitedCount} invited tester${result.invitedCount === 1 ? '' : 's'}. They must sign in with an invited Google account.` : 'Private beta access removed. Existing beta sessions remain isolated for reporting, but testers can no longer open the beta.');
    }, 'Could not configure beta access. Set BETA_RELEASES=true in this Preview environment and keep this release staged.');
  };
  const viewFeedback = (release: AdminReleaseVersion) => run(async () => {
    const items = await getBetaReleaseFeedback(release.releaseId);
    setFeedback((current) => ({ ...current, [release.releaseId]: items }));
    setFeedbackNotes((current) => ({ ...current, ...Object.fromEntries(items.map((item) => [item.feedbackId, item.adminNote])) }));
    onNotice(items.length ? `${items.length} beta feedback item${items.length === 1 ? '' : 's'} loaded below.` : 'No beta feedback has been submitted for this release yet.');
  }, 'Could not load beta feedback.');
  const triage = (release: AdminReleaseVersion, item: BetaFeedback, status: BetaFeedback['status']) => run(async () => {
    const updated = await triageBetaReleaseFeedback(release.releaseId, item.feedbackId, { status, adminNote: feedbackNotes[item.feedbackId] ?? item.adminNote });
    setFeedback((current) => ({ ...current, [release.releaseId]: (current[release.releaseId] ?? []).map((entry) => entry.feedbackId === updated.feedbackId ? updated : entry) }));
    await refresh();
    onNotice(status === 'resolved' ? 'Feedback marked resolved. This remains a private beta record.' : 'Feedback reopened for beta review.');
  }, 'Could not save the feedback review.');
  const recordDecision = (release: AdminReleaseVersion, decision: 'continue_testing' | 'ready_for_release_review') => run(async () => {
    await recordBetaReleaseDecision(release.releaseId, { decision, note: decisionNotes[release.releaseId] ?? '' });
    await refresh();
    onNotice(decision === 'ready_for_release_review' ? 'Beta decision recorded: ready for human release review. This did not publish the story.' : 'Beta decision recorded: continue testing.');
  }, 'Could not record that decision. Resolve all open feedback before marking ready for release review.');
  const approvePublicationReview = (release: AdminReleaseVersion) => run(async () => {
    await approveReleasePublicationReview(release.releaseId, { checksum: release.manifest.sha256, note: publicationNotes[release.releaseId] ?? '' });
    await refresh();
    onNotice('Checksum-bound publication review approval recorded. The story is still not live and no player content changed.');
  }, 'Could not approve publication review. First record “ready for release review” and resolve all open beta feedback.');
  const downloadPublicationHandoff = (release: AdminReleaseVersion) => run(async () => {
    const handoff = await getReleasePublicationHandoff(release.releaseId);
    const url = URL.createObjectURL(new Blob([JSON.stringify(handoff, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `${release.bookId}-controlled-publication-handoff-v${release.version}.json`; link.click(); URL.revokeObjectURL(url);
    onNotice('Downloaded the controlled publication hand-off. It requires trusted-content conversion before any future launch.');
  }, 'Could not create a publication hand-off. First record the controlled publication approval.');
  const checkTrustedCompatibility = (release: AdminReleaseVersion) => run(async () => {
    const result = await getTrustedContentCompatibility(release.releaseId);
    setCompatibility((current) => ({ ...current, [release.releaseId]: result }));
    onNotice(result.summary.eligibleForTrustedConversion ? 'Trusted-content compatibility is clear for conversion work. This still does not publish the story.' : `Trusted-content check found ${result.summary.blockingIssueCount} blocker${result.summary.blockingIssueCount === 1 ? '' : 's'} below.`);
  }, 'Could not check trusted-content compatibility. First record the controlled publication approval.');
  const downloadNarrativeConversion = (release: AdminReleaseVersion) => run(async () => {
    const preview = await getNarrativeConversionPreview(release.releaseId);
    const url = URL.createObjectURL(new Blob([JSON.stringify(preview, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `${release.bookId}-narrative-conversion-preview-v${release.version}.json`; link.click(); URL.revokeObjectURL(url);
    onNotice(`Downloaded narrative conversion preview with ${preview.warnings.length} conversion note${preview.warnings.length === 1 ? '' : 's'}. It is not connected to live player content.`);
  }, 'Could not create the narrative conversion preview. First record the controlled publication approval.');
  const download = (release: AdminReleaseVersion) => run(async () => {
    const snapshot = await getAdminReleaseVersion(release.releaseId);
    const url = URL.createObjectURL(new Blob([JSON.stringify(snapshot, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `${release.bookId}-release-v${release.version}.json`; link.click(); URL.revokeObjectURL(url);
    onNotice(`Downloaded frozen release v${release.version} for review. It is not player-facing.`);
  }, 'Could not download the frozen release snapshot.');

  const bookReleases = (releases ?? []).filter((release) => release.bookId === draft.bookId);
  return <section className="mt-6 rounded-xl border border-[#c5a059]/30 bg-[#150f1f] p-5">
    <div className="flex items-start gap-3"><ShieldCheck className="mt-0.5 h-5 w-5 text-[#e5c158]" /><div><h2 className="font-display text-xl text-[#f5f0e6]">Release registry</h2><p className="mt-1 text-sm text-stone-400">Immutable approved snapshots, staged playtests, and private beta review.</p></div></div>
    {draft.status === 'approved_for_release' ? <button disabled={working} onClick={() => void prepare()} className="mt-4 inline-flex items-center gap-2 rounded border border-emerald-400/60 px-3 py-2 text-sm text-emerald-200 disabled:opacity-50"><PackageCheck className="h-4 w-4" />{working ? 'Preparing…' : 'Freeze release version'}</button> : <p className="mt-4 text-sm text-stone-500">Approve this draft before freezing a release version.</p>}
    <div className="mt-5"><h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#c5a059]"><History className="h-4 w-4" />{draft.bookId} release history</h3>
      {releases === null ? <p className="mt-2 text-sm text-stone-400">Loading release history…</p> : bookReleases.length === 0 ? <p className="mt-2 text-sm text-stone-500">No release versions yet.</p> : <div className="mt-3 grid gap-2">{bookReleases.map((release) => <article key={release.releaseId} className="rounded border border-white/10 bg-black/15 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2"><strong className="text-sm text-[#f5f0e6]">Version {release.version}</strong><span className={release.status === 'staged' ? 'text-xs text-sky-300' : release.status === 'selected' ? 'text-xs text-emerald-300' : 'text-xs text-stone-400'}>{release.status === 'staged' ? (release.betaEnabled ? 'Private beta active' : 'Staging preview active') : release.status === 'selected' ? 'Selected for later rollout' : 'Prepared'}</span></div>
        <p className="mt-1 text-xs text-stone-500">Approved revision {release.source.approvedRevision} · {release.manifest.sceneCount} scenes · checksum {release.manifest.sha256.slice(0, 12)}…</p>
        <div className="mt-3 flex flex-wrap gap-3"><button disabled={working} onClick={() => void download(release)} className="inline-flex items-center gap-2 rounded border border-white/15 px-2 py-1 text-xs text-stone-200 disabled:opacity-50"><Download className="h-3.5 w-3.5" />Download snapshot</button>
          {release.status === 'selected' && <button disabled={working} onClick={() => void stage(release)} className="inline-flex items-center gap-2 rounded border border-sky-400/60 px-2 py-1 text-xs text-sky-200 disabled:opacity-50"><Rocket className="h-3.5 w-3.5" />Stage preview</button>}
          {release.status === 'staged' ? <><button disabled={working} onClick={() => void readiness(release)} className="rounded border border-sky-400/40 px-2 py-1 text-xs text-sky-200 disabled:opacity-50">Staging readiness</button><button disabled={working} onClick={() => void betaReadiness(release)} className="rounded border border-violet-400/40 px-2 py-1 text-xs text-violet-200 disabled:opacity-50">Beta readiness</button><button disabled={working} onClick={() => void checkBetaGate(release)} className="rounded border border-emerald-400/40 px-2 py-1 text-xs text-emerald-200 disabled:opacity-50">Check beta gate</button><button disabled={working} onClick={() => void downloadBetaReport(release)} className="rounded border border-emerald-400/40 px-2 py-1 text-xs text-emerald-200 disabled:opacity-50">Download beta report</button><button disabled={working} onClick={() => void viewFeedback(release)} className="inline-flex items-center gap-1 rounded border border-violet-400/40 px-2 py-1 text-xs text-violet-200 disabled:opacity-50"><MessageSquareText className="h-3.5 w-3.5" />View feedback</button></> : release.status === 'selected' ? <p className="text-xs text-stone-400">Selected by {release.selectedBy}.</p> : <button disabled={working} onClick={() => void select(release)} className="inline-flex items-center gap-2 rounded border border-[#c5a059]/60 px-2 py-1 text-xs text-[#e5c158] disabled:opacity-50"><RotateCcw className="h-3.5 w-3.5" />Select / rollback to this version</button>}</div>
        {betaGates[release.releaseId] && <div className="mt-3 rounded border border-emerald-400/25 bg-black/20 p-3 text-xs text-stone-300"><p className={betaGates[release.releaseId].readyForDecision ? 'font-semibold text-emerald-200' : 'font-semibold text-amber-200'}>{betaGates[release.releaseId].readyForDecision ? 'Beta gate clear for human release review' : 'Beta gate has blockers'}</p><ul className="mt-2 list-disc space-y-1 pl-4"><li className={betaGates[release.releaseId].enabled ? 'text-emerald-200' : 'text-amber-200'}>{betaGates[release.releaseId].enabled ? 'Private beta is enabled' : 'Enable private beta'}</li><li className={betaGates[release.releaseId].sessionCount > 0 ? 'text-emerald-200' : 'text-amber-200'}>{betaGates[release.releaseId].sessionCount > 0 ? `${betaGates[release.releaseId].sessionCount} beta session${betaGates[release.releaseId].sessionCount === 1 ? '' : 's'} recorded` : 'Record at least one beta session'}</li><li className={betaGates[release.releaseId].openFeedbackCount === 0 ? 'text-emerald-200' : 'text-amber-200'}>{betaGates[release.releaseId].openFeedbackCount === 0 ? 'No open feedback' : `Resolve ${betaGates[release.releaseId].openFeedbackCount} open feedback item${betaGates[release.releaseId].openFeedbackCount === 1 ? '' : 's'}`}</li></ul><p className="mt-2 text-stone-500">Checklist only: public release remains off.</p></div>}
        {release.status === 'staged' && <div className="mt-3 rounded border border-violet-400/25 bg-violet-950/15 p-3"><label className="flex items-center gap-2 text-xs font-semibold text-violet-100"><Users className="h-3.5 w-3.5" />Private beta testers</label><textarea value={testerEmails[release.releaseId] ?? ''} onChange={(event) => setTesterEmails((current) => ({ ...current, [release.releaseId]: event.target.value }))} rows={2} placeholder="tester@example.com, another@example.com" className="mt-2 w-full rounded border border-white/15 bg-black/20 p-2 text-xs text-[#f5f0e6]" /><div className="mt-2 flex flex-wrap gap-2"><button disabled={working} onClick={() => void betaAccess(release)} className="rounded border border-violet-400/60 px-2 py-1 text-xs text-violet-100 disabled:opacity-50">Enable / update private beta</button>{release.betaEnabled && <button disabled={working} onClick={() => void betaAccess(release, true)} className="rounded border border-rose-400/50 px-2 py-1 text-xs text-rose-200 disabled:opacity-50">Disable beta</button>}</div><p className="mt-2 text-xs text-stone-400">Saved tester addresses reload here. Invite-only, Google sign-in required.</p></div>}
        {release.status === 'staged' && <div className="mt-3 rounded border border-emerald-400/25 bg-emerald-950/10 p-3"><label className="flex items-center gap-2 text-xs font-semibold text-emerald-100"><CheckCircle2 className="h-3.5 w-3.5" />Private beta decision</label><textarea value={decisionNotes[release.releaseId] ?? release.betaDecision?.note ?? ''} onChange={(event) => setDecisionNotes((current) => ({ ...current, [release.releaseId]: event.target.value }))} rows={2} placeholder="Optional rationale for the release team" className="mt-2 w-full rounded border border-white/15 bg-black/20 p-2 text-xs text-[#f5f0e6]" /><div className="mt-2 flex flex-wrap gap-2"><button disabled={working || !release.betaEnabled} onClick={() => void recordDecision(release, 'continue_testing')} className="rounded border border-amber-300/50 px-2 py-1 text-xs text-amber-100 disabled:opacity-50">Record: continue testing</button><button disabled={working || !release.betaEnabled} onClick={() => void recordDecision(release, 'ready_for_release_review')} className="rounded border border-emerald-400/60 px-2 py-1 text-xs text-emerald-100 disabled:opacity-50">Mark ready for release review</button></div><p className="mt-2 text-xs text-stone-400">{release.betaDecision ? `Latest: ${release.betaDecision.decision.replaceAll('_', ' ')}. ` : ''}“Ready” requires all feedback resolved and never publishes content.</p>{release.betaDecisionHistory?.length ? <div className="mt-2 border-t border-white/10 pt-2 text-xs text-stone-400">{release.betaDecisionHistory.slice().reverse().map((decision) => <p key={`${decision.decidedAt}-${decision.decision}`}>{new Date(decision.decidedAt).toLocaleString()} · {decision.decision.replaceAll('_', ' ')} · {decision.decidedBy}</p>)}</div> : null}</div>}
        {release.status === 'staged' && <div className="mt-3 rounded border border-[#c5a059]/30 bg-black/20 p-3"><label className="flex items-center gap-2 text-xs font-semibold text-[#e5c158]"><ShieldCheck className="h-3.5 w-3.5" />Controlled publication approval</label><textarea value={publicationNotes[release.releaseId] ?? release.publicationApproval?.note ?? ''} onChange={(event) => setPublicationNotes((current) => ({ ...current, [release.releaseId]: event.target.value }))} rows={2} placeholder="Optional final-review note" className="mt-2 w-full rounded border border-white/15 bg-black/20 p-2 text-xs text-[#f5f0e6]" /><div className="mt-2 flex flex-wrap gap-2"><button disabled={working || !release.betaEnabled} onClick={() => void approvePublicationReview(release)} className="rounded border border-[#c5a059]/60 px-2 py-1 text-xs text-[#e5c158] disabled:opacity-50">Approve for controlled publication</button>{release.publicationApproval && <><button disabled={working} onClick={() => void checkTrustedCompatibility(release)} className="rounded border border-violet-400/50 px-2 py-1 text-xs text-violet-200 disabled:opacity-50">Check trusted compatibility</button><button disabled={working} onClick={() => void downloadNarrativeConversion(release)} className="rounded border border-emerald-400/50 px-2 py-1 text-xs text-emerald-200 disabled:opacity-50">Download narrative preview</button><button disabled={working} onClick={() => void downloadPublicationHandoff(release)} className="rounded border border-sky-400/50 px-2 py-1 text-xs text-sky-200 disabled:opacity-50">Download launch hand-off</button></>}</div><p className="mt-2 text-xs text-stone-400">{release.publicationApproval ? `Approved ${new Date(release.publicationApproval.approvedAt).toLocaleString()} for v${release.publicationApproval.version} · checksum ${release.publicationApproval.checksum.slice(0, 12)}…` : 'Requires a clear beta gate and a ready-for-review decision. It is an approval record only, not a launch.'}</p></div>}
        {compatibility[release.releaseId] && <div className="mt-3 rounded border border-violet-400/25 bg-violet-950/10 p-3 text-xs text-stone-300"><p className={compatibility[release.releaseId].summary.eligibleForTrustedConversion ? 'font-semibold text-emerald-200' : 'font-semibold text-amber-200'}>{compatibility[release.releaseId].summary.eligibleForTrustedConversion ? 'Ready for trusted-content conversion' : `${compatibility[release.releaseId].summary.blockingIssueCount} trusted-content blocker${compatibility[release.releaseId].summary.blockingIssueCount === 1 ? '' : 's'}`}</p><p className="mt-1 text-stone-400">Supported effects: {compatibility[release.releaseId].summary.supportedEffectCount} · unsupported: {compatibility[release.releaseId].summary.unsupportedEffectCount}</p>{compatibility[release.releaseId].issues.slice(0, 8).map((issue, index) => <p key={`${issue.code}-${issue.sceneId ?? index}`} className="mt-1 text-stone-300">• {issue.sceneId ? `${issue.sceneId}: ` : ''}{issue.message}</p>)}{compatibility[release.releaseId].issues.length > 8 && <p className="mt-1 text-stone-500">Plus {compatibility[release.releaseId].issues.length - 8} more item(s) in the API report.</p>}<p className="mt-2 text-stone-500">Validation only: the trusted registry and player catalogue remain unchanged.</p></div>}
        {feedback[release.releaseId] && <div className="mt-3 grid gap-2 rounded border border-violet-400/25 bg-black/20 p-3">{feedback[release.releaseId].length ? feedback[release.releaseId].map((item) => <article key={item.feedbackId} className="rounded border border-white/10 p-2"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-xs text-violet-200">{item.testerEmail} · {new Date(item.createdAt).toLocaleString()}</p><span className={item.status === 'resolved' ? 'text-xs text-emerald-300' : 'text-xs text-amber-200'}>{item.status === 'resolved' ? 'Resolved' : 'Open'}</span></div><p className="mt-1 whitespace-pre-wrap text-sm text-stone-200">{item.message}</p><textarea value={feedbackNotes[item.feedbackId] ?? item.adminNote} onChange={(event) => setFeedbackNotes((current) => ({ ...current, [item.feedbackId]: event.target.value }))} rows={2} placeholder="Private admin note" className="mt-2 w-full rounded border border-white/15 bg-black/20 p-2 text-xs text-[#f5f0e6]" /><div className="mt-2"><button disabled={working} onClick={() => void triage(release, item, item.status === 'resolved' ? 'open' : 'resolved')} className="rounded border border-white/20 px-2 py-1 text-xs text-stone-100 disabled:opacity-50">{item.status === 'resolved' ? 'Reopen feedback' : 'Mark resolved'}</button></div></article>) : <p className="text-sm text-stone-400">No feedback yet.</p>}</div>}
      </article>)}</div>}
    </div>
  </section>;
};
