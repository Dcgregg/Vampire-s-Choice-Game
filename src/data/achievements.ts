import { Achievement } from '../types';

export const INITIAL_ACHIEVEMENTS: { [id: string]: Achievement } = {
  THE_STORY_BEGINS: {
    id: 'THE_STORY_BEGINS',
    title: 'The Story Begins',
    description: 'Awaken within the gothic halls of Blackthorn Academy and take your first step into darkness.',
    iconName: 'book-open',
    rarity: 'Common',
  },
  FIRST_CHOICE: {
    id: 'FIRST_CHOICE',
    title: 'First Choice',
    description: 'Make your first fateful decision in the midnight archives.',
    iconName: 'feather',
    rarity: 'Common',
  },
  SECRET_KEEPER: {
    id: 'SECRET_KEEPER',
    title: 'Secret Keeper',
    description: 'Unearth a forbidden truth of the Crimson Seal.',
    iconName: 'key',
    rarity: 'Rare',
  },
  FIRST_BLOOD: {
    id: 'FIRST_BLOOD',
    title: 'First Blood',
    description: 'Conclude Chapter 1 and seal your fate with the Nocturne Covenant.',
    iconName: 'droplet',
    rarity: 'Rare',
  },
  DANGEROUS_LIAISON: {
    id: 'DANGEROUS_LIAISON',
    title: 'Dangerous Liaison',
    description: 'Forge an intense bond by raising any character relationship affinity to 70 or higher.',
    iconName: 'heart',
    rarity: 'Gothic Legend',
  },
  SHADOW_SOVEREIGN: {
    id: 'SHADOW_SOVEREIGN',
    title: 'Shadow Sovereign',
    description: 'Navigate the climax of the Solstice Masquerade and declare your allegiance.',
    iconName: 'crown',
    rarity: 'Gothic Legend',
  },
};
