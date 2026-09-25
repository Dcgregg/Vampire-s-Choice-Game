export type TestPronouns = 'she' | 'he' | 'they';

const forms: Record<TestPronouns, { subject: string; object: string; possessive: string }> = {
  she: { subject: 'she', object: 'her', possessive: 'her' },
  he: { subject: 'he', object: 'him', possessive: 'his' },
  they: { subject: 'they', object: 'them', possessive: 'their' },
};

export function resolveStoryTokens(text: string, playerName: string, pronouns: TestPronouns, species = 'Human', speakerName?: string): string {
  const player = forms[pronouns];
  const tokens: Record<string, string> = { 'player.name': playerName || 'Player', 'player.subject': player.subject, 'player.object': player.object, 'player.possessive': player.possessive, 'player.species': species || 'Human', 'speaker.name': speakerName || 'Unknown speaker' };
  return text.replace(/{{\s*([A-Za-z][A-Za-z0-9_.-]*)\s*}}/g, (whole, key: string) => tokens[key] ?? whole);
}
