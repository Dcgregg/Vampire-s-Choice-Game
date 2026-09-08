import { Character } from '../types';

export const INITIAL_CHARACTERS: { [characterId: string]: Character } = {
  lucian: {
    id: 'lucian',
    name: 'Lord Lucian Cross',
    title: 'Chancellor of Antiquities & Elder Aristocrat',
    description:
      'Ancient and formidable, Lucian commands the nocturnal corridors of Blackthorn with quiet elegance. Behind his cultured obsidian gaze lies centuries of whispered covenants.',
    avatar: 'lucian',
    affinity: 50,
    romanceEligible: true,
    status: 'Acquaintance',
    loreUnlocked: ['Bearer of the House of Cross signet', 'Keeper of the Obsidian Vault'],
  },
  isolde: {
    id: 'isolde',
    name: 'Lady Isolde Vance',
    title: 'Master Archivist & Alchemist',
    description:
      'A brilliant dhampir scholar whose silver-pinned braids and leather apothecary gloves conceal a fierce protective streak for mortals caught in supernatural tides.',
    avatar: 'isolde',
    affinity: 45,
    romanceEligible: true,
    status: 'Acquaintance',
    loreUnlocked: ['Guardian of the Crimson Runes', 'Distiller of Silver Elixirs'],
  },
  nico: {
    id: 'nico',
    name: 'Nicholas "Nico" Drake',
    title: 'Investigative Mortal Scholar',
    description:
      'Warm-eyed, clever, and stubbornly loyal. Nico seeks the truth behind his elder sister’s sudden disappearance into the Blackthorn shadows.',
    avatar: 'nico',
    affinity: 50,
    romanceEligible: true,
    status: 'Acquaintance',
    loreUnlocked: ['Junior Fellow of Medieval Epigraphy', 'Possesses his sister’s journal'],
  },
  marcella: {
    id: 'marcella',
    name: 'Sister Marcella',
    title: 'Emissary of the Silver Dawn',
    description:
      'An enigmatic watcher draped in ash-grey silks. She represents the historic truce between mortals and the nightborn—ever ready to enforce the covenant.',
    avatar: 'marcella',
    affinity: 35,
    romanceEligible: false,
    status: 'Unknown',
    loreUnlocked: ['Observer sent by the High Council'],
  },
};
