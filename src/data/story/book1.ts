import { Book, Scene } from '../../types';

export const BOOK_1: Book = {
  id: 'book1',
  title: 'Bloodlines of Blackthorn',
  subtitle: 'Book I: The Nocturne Covenant',
  synopsis:
    'Summoned to the mist-draped cloisters of Blackthorn Academy on a scholarship of ancient lore, you discover that the university’s aristocratic founders never truly passed into the grave. Between forbidden manuscripts, moonlit masquerades, and mortal conspiracies, every allegiance is bought with blood.',
  coverArtStyle: 'gothic-castle-moonlight',
  chapters: [
    {
      number: 1,
      title: 'The Whispering Library',
      summary: 'A midnight arrival, a shadowed corridor, and an ancient covenant unsealed.',
      firstSceneId: 'b1_c1_s1',
      totalScenes: 4,
      rewardCoins: 50,
      completionAchievementId: 'FIRST_BLOOD',
    },
    {
      number: 2,
      title: 'The Nocturne Masquerade',
      summary: 'Velvet masks, poisoned crystal goblets, and whispered confessions upon the moonlit balcony.',
      firstSceneId: 'b1_c2_s1',
      totalScenes: 4,
      rewardCoins: 60,
      completionAchievementId: 'SECRET_KEEPER',
    },
    {
      number: 3,
      title: 'The Eclipse of Thorns',
      summary: 'The catacombs open beneath Blackthorn. Will you preserve the masquerade or shatter the nightborn empire?',
      firstSceneId: 'b1_c3_s1',
      totalScenes: 4,
      rewardCoins: 100,
      completionAchievementId: 'SHADOW_SOVEREIGN',
    },
  ],
};

export const SCENES: { [sceneId: string]: Scene } = {
  // ==========================================
  // CHAPTER 1: THE WHISPERING LIBRARY
  // ==========================================

  b1_c1_s1: {
    id: 'b1_c1_s1',
    bookId: 'book1',
    chapterNumber: 1,
    chapterTitle: 'The Whispering Library',
    sceneTitle: 'Midnight at the Gates',
    sceneIndex: 1,
    paragraphs: [
      'The iron wrought gates of Blackthorn Academy loomed into the torrential mist like jagged teeth against a bruised violet sky. You gripped the parchment invitation tightly in your gloved fingers, the crimson wax seal still warm to the touch.',
      'Inside the Great Scriptorium, candlelight danced over towering shelves of calfskin folio volumes and obsidian bust statues whose stone eyes seemed to follow your stride.',
      'Suddenly, an iron hinge groans in the lower cloister. A tall silhouette, cloaked in heavy dark wool with silver cuffs, slips silently past the velvet drapes toward the forbidden underground archives.',
      'A draft of air scented with crushed rose petals and damp stone drifts past your cheek. You are supposed to report to the Proctor’s lodge... but the quiet magnetism of that descending shadow makes your pulse quicken.',
    ],
    choices: [
      {
        id: 'c1_pursue_shadow',
        text: 'Pursue the stranger through the lower wrought-iron archway.',
        nextSceneId: 'b1_c1_s2a',
        consequencesSummary: 'Follow into the Crypt Library and confront the aristocratic figure.',
        effects: {
          relationshipChanges: { lucian: 6 },
          setFlags: { pursuedShadow: true, metLucian: true },
          achievementId: 'FIRST_CHOICE',
          notificationText: 'Lucian noticed your stealthy pursuit.',
        },
      },
      {
        id: 'c1_investigate_lectern',
        text: 'Remain in the scriptorium and inspect the illuminated grimoire on the lectern.',
        nextSceneId: 'b1_c1_s2b',
        consequencesSummary: 'Decipher the blood-ink runes and cross paths with the Master Archivist.',
        effects: {
          relationshipChanges: { isolde: 6 },
          setFlags: { studiedGrimoire: true, metIsolde: true, hasSilverKey: true },
          achievementId: 'FIRST_CHOICE',
          notificationText: 'Isolde approves of scholarly caution. Acquired: Silver Key.',
        },
      },
      {
        id: 'c1_call_out',
        text: 'Call out into the darkness and steady your footing.',
        nextSceneId: 'b1_c1_s2c',
        consequencesSummary: 'Sound the alarm in the quiet halls, drawing an unexpected human ally.',
        effects: {
          relationshipChanges: { nico: 6 },
          setFlags: { alertedGuard: true, metNico: true },
          achievementId: 'FIRST_CHOICE',
          notificationText: 'Nico rushed to intercept before the night sentinels awoke.',
        },
      },
    ],
  },

  // SCENE 2A: The Cloistered Crypt (Lucian Branch)
  b1_c1_s2a: {
    id: 'b1_c1_s2a',
    bookId: 'book1',
    chapterNumber: 1,
    chapterTitle: 'The Whispering Library',
    sceneTitle: 'The Cloistered Crypt',
    sceneIndex: 2,
    paragraphs: [
      'Your boots make barely a murmur on the cold granite stairs descending into the crypt library. The air here is frigid, untouched by the season outside.',
      'At the center of a circular vault ringed by wax-dripping candelabras stands the figure. As he turns, the soft amber glow catches high, aristocratic cheekbones, an obsidian cravat, and eyes the color of crushed amethysts.',
      'He looks at you not with alarm, but with the cool curiosity of an immortal who has not been surprised in three hundred years.',
    ],
    dialogues: [
      {
        speaker: 'Lord Lucian Cross',
        text: 'Few mortals possess both the audacity to follow me and the grace to do so without echoing across the stone. You must be [NAME]. Our newest scholar of antiquities.',
        characterId: 'lucian',
        mood: 'whisper',
      },
      {
        speaker: 'Lord Lucian Cross',
        text: 'Tell me, [NAME]... did you come down here seeking truth, or merely looking for someone to save you from the rain?',
        characterId: 'lucian',
        mood: 'romantic',
      },
    ],
    choices: [
      {
        id: 'c2a_stand_ground',
        text: 'Step forward without flinching and meet his gaze directly.',
        nextSceneId: 'b1_c1_s3',
        consequencesSummary: 'Establish yourself as fearless before the ancient elder.',
        isRomantic: true,
        effects: {
          relationshipChanges: { lucian: 8 },
          setFlags: { trustedLucian: true, boldEntrance: true },
          coinsChange: 15,
          notificationText: 'Lucian is deeply intrigued by your quiet defiance. (+8)',
        },
      },
      {
        id: 'c2a_demand_answers',
        text: 'Keep your hand near your collar and demand why he prowls the crypts at midnight.',
        nextSceneId: 'b1_c1_s3',
        consequencesSummary: 'Show analytical wariness; keep your emotional distance.',
        effects: {
          relationshipChanges: { lucian: 3, isolde: 2 },
          setFlags: { waryOfLucian: true },
          notificationText: 'Lucian respects your guarded instinct.',
        },
      },
    ],
  },

  // SCENE 2B: The Forbidden Lectern (Isolde Branch)
  b1_c1_s2b: {
    id: 'b1_c1_s2b',
    bookId: 'book1',
    chapterNumber: 1,
    chapterTitle: 'The Whispering Library',
    sceneTitle: 'The Forbidden Lectern',
    sceneIndex: 2,
    paragraphs: [
      'You step softly toward the heavy brass lectern. The book bound in dark burgundy leather lies open beneath a glass lantern. The script is penned in a deep vermilion ink that glistens as if newly drawn.',
      'Before your fingers can brush the vellum, the faint hiss of an unsheathing silver dagger freezes you in place.',
      'From behind the marble pillar steps a woman with raven hair braided with delicate silver pins. Leather alchemical gloves encase her hands, and her amber eyes narrow with clinical precision.',
    ],
    dialogues: [
      {
        speaker: 'Lady Isolde Vance',
        text: 'Touch that vellum with bare skin, scholar, and the ward will strip the breath from your lungs before you reach the second line.',
        characterId: 'isolde',
        mood: 'warning',
      },
      {
        speaker: 'Lady Isolde Vance',
        text: 'You have the face of the newcomer, [NAME]. If you are here to pillage our archives, speak now, or find yourself locked in the dispensary till dawn.',
        characterId: 'isolde',
        mood: 'neutral',
      },
    ],
    choices: [
      {
        id: 'c2b_translate_rune',
        text: 'Decipher the inscription aloud: "Through blood and silver, truth endures."',
        nextSceneId: 'b1_c1_s3',
        consequencesSummary: 'Prove your rare linguistic talent and impress the Master Archivist.',
        isRomantic: true,
        effects: {
          relationshipChanges: { isolde: 9 },
          setFlags: { decipheredRune: true, respectedByIsolde: true },
          coinsChange: 20,
          notificationText: 'Isolde lowers her blade in genuine scholarly admiration. (+9)',
        },
      },
      {
        id: 'c2b_step_back',
        text: 'Step back with open palms and offer a courteous apology for intruding.',
        nextSceneId: 'b1_c1_s3',
        consequencesSummary: 'Demonstrate disciplined etiquette and respect for boundaries.',
        effects: {
          relationshipChanges: { isolde: 4 },
          setFlags: { respectfulStudent: true },
          notificationText: 'Isolde nods curtly, accepting your composure.',
        },
      },
    ],
  },

  // SCENE 2C: The Scholar\'s Alcove (Nico Branch)
  b1_c1_s2c: {
    id: 'b1_c1_s2c',
    bookId: 'book1',
    chapterNumber: 1,
    chapterTitle: 'The Whispering Library',
    sceneTitle: "The Scholar's Alcove",
    sceneIndex: 2,
    paragraphs: [
      'Your voice echoes against the high vaulted timber ceiling: "Is someone there?"',
      'Before the echo fades, a warm hand grabs your wrist and yanks you behind a heavy velvet drapery inside a dusty display alcove. A tall young man with tousled copper hair and ink-splattered cuffs presses a finger to his lips.',
      'Two campus night sentinels in dark grey cloaks march through the arched hall outside, lanterns swaying, before their footsteps recede into the east wing.',
    ],
    dialogues: [
      {
        speaker: 'Nico Drake',
        text: 'Are you out of your mind? If Sister Marcella’s night patrols caught you wandering unescorted past curfew, you’d be on the first carriage back to the coast.',
        characterId: 'nico',
        mood: 'whisper',
      },
      {
        speaker: 'Nico Drake',
        text: 'Wait... you are [NAME], aren’t you? The one who solved the Blackthorn admission cipher? I’m Nico. And right now, we need to move before the real masters wake up.',
        characterId: 'nico',
        mood: 'romantic',
      },
    ],
    choices: [
      {
        id: 'c2c_stay_close',
        text: 'Lean into the shadowed alcove and thank him with a steady smile.',
        nextSceneId: 'b1_c1_s3',
        consequencesSummary: 'Create an intimate spark with the investigative mortal scholar.',
        isRomantic: true,
        effects: {
          relationshipChanges: { nico: 8 },
          setFlags: { closeToNico: true, protectedByNico: true },
          coinsChange: 15,
          notificationText: 'Nico flushes slightly in the dark, his grip lingering. (+8)',
        },
      },
      {
        id: 'c2c_demand_truth',
        text: 'Politely free your wrist and ask why he is hiding in the shadows himself.',
        nextSceneId: 'b1_c1_s3',
        consequencesSummary: 'Show sharp perception and mutual curiosity.',
        effects: {
          relationshipChanges: { nico: 4, isolde: 2 },
          setFlags: { questionedNico: true },
          notificationText: 'Nico grins sheepishly at your keen eye.',
        },
      },
    ],
  },

  // SCENE 3: The Crimson Covenant
  b1_c1_s3: {
    id: 'b1_c1_s3',
    bookId: 'book1',
    chapterNumber: 1,
    chapterTitle: 'The Whispering Library',
    sceneTitle: 'The Broken Ward',
    sceneIndex: 3,
    paragraphs: [
      'You are drawn toward the High Octagonal Chamber beneath the central dome. The air vibrates with a low harmonic hum that rattles your teeth.',
      'In the center of the stone floor, a ring of etched silver runes surrounds an ancient black marble plinth. A fissure has cracked across its surface, weeping a fine vapor the color of freshly spilled wine.',
    ],
    conditionParagraphs: [
      {
        conditionFlag: 'trustedLucian',
        paragraphs: [
          'Lucian stands beside you, his dark cloak brushing yours. "The seal weakens," he whispers, his voice like velvet over steel. "You feel it too, don’t you, [NAME]? Your blood hums with the resonance of the first architects."',
        ],
      },
      {
        conditionFlag: 'studiedGrimoire',
        paragraphs: [
          'Isolde kneels near the silver boundary line, uncorking a vial of pale luminescence. "The warning in the grimoire was literal," she murmurs to you. "Someone inside Blackthorn deliberately shattered the binding glyph."',
        ],
      },
      {
        conditionFlag: 'closeToNico',
        paragraphs: [
          'Nico grips an antique brass compass whose needle spins erratically. "My sister had drawings of this exact plinth in her final journal," he mutters, standing shoulder-to-shoulder with you.',
        ],
      },
    ],
    dialogues: [
      {
        speaker: 'Sister Marcella',
        text: 'Step back from the circle, all of you! The covenant of 1492 cannot withstand careless mortal meddling!',
        characterId: 'marcella',
        mood: 'warning',
      },
    ],
    choices: [
      {
        id: 'c3_blood_resonance',
        text: 'Offer your own palm to test the resonance of the cracked ward.',
        nextSceneId: 'b1_c1_s4',
        consequencesSummary: 'Risk your own vitality to silence the rift; win the awe of the nightborn.',
        isDangerous: true,
        effects: {
          relationshipChanges: { lucian: 8, isolde: 5 },
          setFlags: { offeredBloodResonance: true, knowsVampireSecret: true },
          coinsChange: 30,
          notificationText: 'The crimson vapor purrs at your touch. Supernatural secret revealed!',
        },
      },
      {
        id: 'c3_alchemical_seal',
        text: 'Assist Isolde in deploying the silver reagents to safely bind the rupture.',
        nextSceneId: 'b1_c1_s4',
        consequencesSummary: 'Take the scientific, tactical approach to restore order.',
        effects: {
          relationshipChanges: { isolde: 9, nico: 4 },
          setFlags: { usedAlchemy: true, restoredWardOrder: true },
          coinsChange: 25,
          notificationText: 'Isolde marvels at your steady hand under supernatural pressure. (+9)',
        },
      },
      {
        id: 'c3_protect_nico',
        text: 'Shield Nico and memorize the arcane sigils etched into the stone.',
        nextSceneId: 'b1_c1_s4',
        consequencesSummary: 'Prioritize human safety and commit the secret runes to memory.',
        effects: {
          relationshipChanges: { nico: 9, lucian: 2 },
          setFlags: { protectedNico: true, memorizedSigil: true },
          coinsChange: 20,
          notificationText: 'Nico looks at you with profound, unspoken gratitude. (+9)',
        },
      },
    ],
  },

  // SCENE 4: Chapter 1 Conclusion & The Blood Oath
  b1_c1_s4: {
    id: 'b1_c1_s4',
    bookId: 'book1',
    chapterNumber: 1,
    chapterTitle: 'The Whispering Library',
    sceneTitle: 'The Midnight Vow',
    sceneIndex: 4,
    paragraphs: [
      'The crimson vapors recede into the cracks of the black marble, leaving the chamber in heavy, suspended silence.',
      'Lord Lucian Cross steps forward into the dim candlelight, his violet eyes locked onto yours with unmistakable intensity. He offers a heavy signet ring bearing an onyx raven with rubies for eyes.',
      '"You have proven that your presence here is no accident of admissions, [NAME]," Lucian murmurs. "The founders have taken notice. When the Solstice Masquerade convenes tomorrow evening, you will not attend as a mere bystander."',
      'Behind him, Isolde gives you a slow, solemn nod of respect, while Nico whispers: "Whatever this game is, [NAME]... we’re in it together now."',
      'The tolling of the midnight bell echoes through Blackthorn Manor. Your first night has ended, but your fate among the immortals has only just begun.',
    ],
    choices: [
      {
        id: 'c4_accept_token',
        text: 'Accept the onyx signet ring and seal your place at Blackthorn.',
        nextSceneId: 'b1_c2_s1',
        consequencesSummary: 'Complete Chapter 1 and prepare for the Solstice Masquerade.',
        effects: {
          relationshipChanges: { lucian: 5 },
          setFlags: { acceptedSignet: true, completedChapter1: true },
          coinsChange: 50,
          achievementId: 'FIRST_BLOOD',
          notificationText: 'Chapter 1 Complete! Unlocked Achievement: First Blood (+50 Coins)',
        },
      },
      {
        id: 'c4_vow_independence',
        text: 'Touch the ring in courtesy, but declare you walk your own path.',
        nextSceneId: 'b1_c2_s1',
        consequencesSummary: 'Assert your independence to both immortals and mortals alike.',
        effects: {
          relationshipChanges: { nico: 5, isolde: 5 },
          setFlags: { independentPath: true, completedChapter1: true },
          coinsChange: 50,
          achievementId: 'FIRST_BLOOD',
          notificationText: 'Chapter 1 Complete! Unlocked Achievement: First Blood (+50 Coins)',
        },
      },
    ],
  },

  // ==========================================
  // CHAPTER 2: THE NOCTURNE MASQUERADE
  // ==========================================

  b1_c2_s1: {
    id: 'b1_c2_s1',
    bookId: 'book1',
    chapterNumber: 2,
    chapterTitle: 'The Nocturne Masquerade',
    sceneTitle: 'The Velvet Ballroom',
    sceneIndex: 1,
    paragraphs: [
      'The Grand Ballroom of Blackthorn Manor is transformed into a sea of silk, velvet, and dark feathered plumage. Giant crystal chandeliers hang low, their candles casting long, predatory shadows across the mirrored parquet floor.',
      'Every attendee wears an ornate masquerade mask. Mortals and vampires mingle under the ancient truce, their laughter masking centuries of unspoken vendettas.',
      'Upon entering, a silver tray of handcrafted masks is presented to you by a cloaked attendant.',
    ],
    choices: [
      {
        id: 'c2_1_crimson_mask',
        text: 'Select the Venetian mask of crimson lacquer laced with black filigree.',
        nextSceneId: 'b1_c2_s2',
        consequencesSummary: 'Wear the emblem of passionate defiance and romantic intrigue.',
        isRomantic: true,
        effects: {
          relationshipChanges: { lucian: 5 },
          setFlags: { woreCrimsonMask: true },
          notificationText: 'Lucian tracks your entrance with smoldering approval.',
        },
      },
      {
        id: 'c2_1_silver_mask',
        text: 'Select the silver owl mask adorned with delicate apothecary herbs.',
        nextSceneId: 'b1_c2_s2',
        consequencesSummary: 'Wear the emblem of wisdom and alchemical mastery.',
        effects: {
          relationshipChanges: { isolde: 5 },
          setFlags: { woreSilverMask: true },
          notificationText: 'Isolde raises her goblet to your chosen motif.',
        },
      },
      {
        id: 'c2_1_midnight_mask',
        text: 'Select the sleek midnight-charcoal mask with discreet bronze gears.',
        nextSceneId: 'b1_c2_s2',
        consequencesSummary: 'Blend into the shadows with the inquisitive scholars.',
        effects: {
          relationshipChanges: { nico: 5 },
          setFlags: { woreMidnightMask: true },
          notificationText: 'Nico recognizes your styling immediately through the throng.',
        },
      },
    ],
  },

  b1_c2_s2: {
    id: 'b1_c2_s2',
    bookId: 'book1',
    chapterNumber: 2,
    chapterTitle: 'The Nocturne Masquerade',
    sceneTitle: 'The Waltz of Shadows',
    sceneIndex: 2,
    paragraphs: [
      'A minor-key waltz begins to swirl from the orchestra balcony. The violins rise in a slow, intoxicating rhythm that makes the candlelight seem to dip and sway.',
      'As the dancers pair off, a gloved hand reaches toward you from behind the velvet column.',
    ],
    dialogues: [
      {
        speaker: 'Lord Lucian Cross',
        text: 'A dance, [NAME]? Or do you fear what happens when two people let down their guards in a room full of hungry eyes?',
        characterId: 'lucian',
        mood: 'romantic',
      },
    ],
    choices: [
      {
        id: 'c2_2_dance_lucian',
        text: 'Take Lucian’s hand and let him guide you onto the center floor.',
        nextSceneId: 'b1_c2_s3',
        consequencesSummary: 'Share an intoxicating, breathless dance with the elder vampire.',
        isRomantic: true,
        effects: {
          relationshipChanges: { lucian: 10 },
          setFlags: { dancedWithLucian: true },
          achievementId: 'DANGEROUS_LIAISON',
          notificationText: 'Lucian pulls you close. Heartbeats and eternal stillness align. (+10)',
        },
      },
      {
        id: 'c2_2_slip_to_isolde',
        text: 'Excuse yourself to the terrace where Isolde watches the perimeter.',
        nextSceneId: 'b1_c2_s3',
        consequencesSummary: 'Join Isolde in the crisp night air to discuss the night’s hidden dangers.',
        isRomantic: true,
        effects: {
          relationshipChanges: { isolde: 8 },
          setFlags: { joinedIsoldeOnTerrace: true },
          notificationText: 'Isolde offers a warm fur stole and confides her suspicions. (+8)',
        },
      },
      {
        id: 'c2_2_intercept_nico',
        text: 'Signal Nico to slip away toward the Chancellor’s private gallery.',
        nextSceneId: 'b1_c2_s3',
        consequencesSummary: 'Seize the distraction of the waltz to hunt for confidential evidence.',
        effects: {
          relationshipChanges: { nico: 8 },
          setFlags: { investigatedWithNico: true },
          notificationText: 'Nico cracks a sly smile as you bypass the velvet rope together. (+8)',
        },
      },
    ],
  },

  b1_c2_s3: {
    id: 'b1_c2_s3',
    bookId: 'book1',
    chapterNumber: 2,
    chapterTitle: 'The Nocturne Masquerade',
    sceneTitle: 'The Poisoned Chalice',
    sceneIndex: 3,
    paragraphs: [
      'A footman in a porcelain jester mask approaches with a tray of silver goblets filled with aged vintage spiced with cloves. As he offers one to you, you catch the faint, bitter almond scent of wolfsbane distillate.',
      'Across the room, Sister Marcella’s silver veil turns toward you. Someone has orchestrated an assassination attempt disguised as a toast.',
    ],
    choices: [
      {
        id: 'c2_3_expose_traitor',
        text: 'Catch the footman’s wrist and expose the tainted vintage before the court.',
        nextSceneId: 'b1_c2_s4',
        consequencesSummary: 'Shatter the masquerade’s decorum and force the conspirators into the open.',
        isDangerous: true,
        effects: {
          relationshipChanges: { lucian: 6, isolde: 6 },
          setFlags: { exposedConspiracy: true },
          coinsChange: 35,
          notificationText: 'The masquerade freezes in stunned silence as the glass shatters.',
        },
      },
      {
        id: 'c2_3_quiet_swap',
        text: 'Subtly exchange the poisoned goblet with a decanter on the sideboard.',
        nextSceneId: 'b1_c2_s4',
        consequencesSummary: 'Demonstrate quiet cunning and pocket the poisoned draught for testing.',
        effects: {
          relationshipChanges: { isolde: 8, nico: 5 },
          setFlags: { preservedEvidence: true, hasPoisonVial: true },
          coinsChange: 30,
          notificationText: 'Acquired: Poisoned Draught evidence. Isolde is thrilled.',
        },
      },
    ],
  },

  b1_c2_s4: {
    id: 'b1_c2_s4',
    bookId: 'book1',
    chapterNumber: 2,
    chapterTitle: 'The Nocturne Masquerade',
    sceneTitle: 'The Moonlit Balcony',
    sceneIndex: 4,
    paragraphs: [
      'You retreat to the high stone balcony overlooking the misty cliffs of Oakhaven. The winter moon hangs overhead, haloed in faint crimson rings.',
      'The quiet after the masquerade’s music is absolute. Here above the world, the true stakes of Blackthorn are laid bare.',
      '"You saved more than just a mortal reputation tonight, [NAME],"' +
        ' says a voice behind you. Under the stars, the ancient pact that binds mortals and vampires is unspooling, and your name is written at the center of the prophecy.',
    ],
    choices: [
      {
        id: 'c2_4_embrace_destiny',
        text: 'Step to the stone parapet and declare you will unravel the whole mystery.',
        nextSceneId: 'b1_c3_s1',
        consequencesSummary: 'Conclude Chapter 2 with fierce resolve.',
        effects: {
          relationshipChanges: { lucian: 5, isolde: 5, nico: 5 },
          setFlags: { completedChapter2: true },
          coinsChange: 60,
          achievementId: 'SECRET_KEEPER',
          notificationText: 'Chapter 2 Complete! Unlocked Achievement: Secret Keeper (+60 Coins)',
        },
      },
    ],
  },

  // ==========================================
  // CHAPTER 3: THE ECLIPSE OF THORNS
  // ==========================================

  b1_c3_s1: {
    id: 'b1_c3_s1',
    bookId: 'book1',
    chapterNumber: 3,
    chapterTitle: 'The Eclipse of Thorns',
    sceneTitle: 'The Catacombs Unsealed',
    sceneIndex: 1,
    paragraphs: [
      'The Great Eclipse begins. As the moon slides across the sun, daylight bleeds into an eerie, twilight gloom across Blackthorn.',
      'The foundation stones of the Academy groan as the iron seals on the lowest crypts break open. A renegade faction of the Nightborn, tired of centuries of peaceful coexistence with mortals, makes their bid for total dominion.',
      'You stand in the central courtyard as gargoyles shudder on the parapets. Lucian, Isolde, and Nico gather around you, their weapons readied.',
    ],
    choices: [
      {
        id: 'c3_1_lead_charge',
        text: 'Take command of the defense: "We protect both mortal and vampire alike."',
        nextSceneId: 'b1_c3_s2',
        consequencesSummary: 'Unite the faction leaders under your sovereign vision.',
        effects: {
          relationshipChanges: { lucian: 6, isolde: 6, nico: 6 },
          setFlags: { unifiedLeadership: true },
          coinsChange: 30,
          notificationText: 'Your allies draw courage from your unwavering authority.',
        },
      },
      {
        id: 'c3_1_flank_underground',
        text: 'Propose an underground flank through the forgotten catacomb canals.',
        nextSceneId: 'b1_c3_s2',
        consequencesSummary: 'Infiltrate behind the renegade lines to strike at the heart of the ritual.',
        effects: {
          relationshipChanges: { isolde: 8, nico: 6 },
          setFlags: { flakedCatacombs: true },
          coinsChange: 35,
          notificationText: 'Tactical brilliance. The infiltration begins unnoticed.',
        },
      },
    ],
  },

  b1_c3_s2: {
    id: 'b1_c3_s2',
    bookId: 'book1',
    chapterNumber: 3,
    chapterTitle: 'The Eclipse of Thorns',
    sceneTitle: 'The Choice of Allegiance',
    sceneIndex: 2,
    paragraphs: [
      'In the sunken Heart Chamber beneath the roots of the Blackthorn tree, the Arch-Rebel Lord Valerius channels the eclipse’s dark energy into the Obsidian Chalice.',
      'To break the ritual, someone must bind their blood to the ancient Blackthorn seal. It will permanently tie their destiny to the eternal throne of the night.',
      'Lucian steps forward, his hand outheld: "I would share the burden of eternity with no one else, [NAME]. But the choice must be entirely yours."',
      'Isolde holds an alchemical counter-seal: "You can neutralize it and remain untamed, [NAME]. You owe them no eternal chains."',
      'Nico looks at you, eyes wide with fierce devotion: "Whatever you decide, [NAME]... I will stand beside you until dawn."',
    ],
    choices: [
      {
        id: 'c3_2_vampire_embrace',
        text: 'Take Lucian’s hand and drink from the Chalice of the Eclipse.',
        nextSceneId: 'b1_c3_s3',
        consequencesSummary: 'Awaken the latent royal bloodline and ascend as a nocturnal sovereign.',
        isRomantic: true,
        isDangerous: true,
        effects: {
          relationshipChanges: { lucian: 15, nico: -2 },
          setFlags: { ascendedNocturneSovereign: true, chosenPartner: 'lucian' },
          achievementId: 'SHADOW_SOVEREIGN',
          notificationText: 'You and Lucian ascend as Sovereigns of Blackthorn! (+15 Lucian)',
        },
      },
      {
        id: 'c3_2_alchemical_balance',
        text: 'Shatter the Chalice with Isolde’s silver reagent, sealing the breach forever.',
        nextSceneId: 'b1_c3_s3',
        consequencesSummary: 'Preserve the fragile balance between humanity and the nightborn.',
        isRomantic: true,
        effects: {
          relationshipChanges: { isolde: 15, lucian: 5 },
          setFlags: { preservedBalance: true, chosenPartner: 'isolde' },
          achievementId: 'SHADOW_SOVEREIGN',
          notificationText: 'Isolde clasps your hand as the crimson magic neutralizes into starlight. (+15)',
        },
      },
      {
        id: 'c3_2_mortal_defiance',
        text: 'Rescue Nico’s family records and declare Blackthorn open to the mortal world.',
        nextSceneId: 'b1_c3_s3',
        consequencesSummary: 'Break the secrecy of centuries and usher in a new era of mortal courage.',
        isRomantic: true,
        effects: {
          relationshipChanges: { nico: 15, lucian: -2 },
          setFlags: { mortalReformation: true, chosenPartner: 'nico' },
          achievementId: 'SHADOW_SOVEREIGN',
          notificationText: 'Nico embraces you in the dawning light. The age of secrecy ends. (+15)',
        },
      },
    ],
  },

  b1_c3_s3: {
    id: 'b1_c3_s3',
    bookId: 'book1',
    chapterNumber: 3,
    chapterTitle: 'The Eclipse of Thorns',
    sceneTitle: 'The Dawning Eclipse',
    sceneIndex: 3,
    paragraphs: [
      'The eclipse passes. Golden rays of dawn cut through the stained-glass arches of Blackthorn, washing over stone scarred by magic and sword alike.',
      'Silence falls across the grand courtyard. The students and immortals emerge from the shadows, looking upon you not merely as a scholar, but as the one who decided the fate of their realm.',
    ],
    conditionParagraphs: [
      {
        conditionFlag: 'ascendedNocturneSovereign',
        paragraphs: [
          'Lucian stands at your side, cloaked in royal crimson and velvet. His cool fingers clasp yours as the court kneels in reverence. "The night now belongs to us, [NAME]. And eternity has only just begun."',
        ],
      },
      {
        conditionFlag: 'preservedBalance',
        paragraphs: [
          'Isolde wipes silver dust from her brow and offers a rare, radiant smile. "You did what no scholar before you could. You held the line between two worlds, [NAME]. Blackthorn owes you its soul."',
        ],
      },
      {
        conditionFlag: 'mortalReformation',
        paragraphs: [
          'Nico stands beside you under the warm morning sun, laughing in relief as the campus bells ring out clear and true. "We actually did it, [NAME]. We changed everything."',
        ],
      },
    ],
    choices: [
      {
        id: 'c3_3_conclude_book1',
        text: 'Reflect upon your journey and prepare for Book II: The Crimson Throne.',
        nextSceneId: 'b1_c3_s3',
        returnToLanding: true,
        consequencesSummary: 'Complete Book 1 with all choices, flags, and relationships recorded.',
        effects: {
          coinsChange: 100,
          setFlags: { completedBook1: true },
          notificationText: 'Book I: Bloodlines of Blackthorn Complete! (+100 Blood Coins)',
        },
      },
    ],
  },
};
